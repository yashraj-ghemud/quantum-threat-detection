"""
server/services/workers.py
==========================
Background loops (asyncio tasks; compute runs in a thread pool):

- TrafficController   live legitimate signing traffic, with an idle pause
- reservoir loop      keeps each group's ACTIVE bundle count at its target
- CampaignRunner      attack campaigns mixed into live traffic
- block loop          seals ledger blocks
- metrics loop        1 Hz ``metrics.tick`` while clients are connected
- prune loop          retention of reports, nonces, monitor rows and keystore files
"""

from __future__ import annotations

import asyncio
import logging
import secrets
import time
import uuid
from typing import Optional

from sentinel.adversary.catalog import catalog_entry

__all__ = ["TrafficController", "CampaignRunner", "Workers", "CAMPAIGN_PRESETS"]

log = logging.getLogger("qveris.workers")

CAMPAIGN_PRESETS = {
    "low_and_slow": {"name": "Low & slow", "description": "Barely-there channel tampering that only the CUSUM monitor accumulates.",
                     "mix": [{"attack": {"attack_id": "channel.depolarize", "intensity": 0.03}, "weight": 1}]},
    "blitz": {"name": "Blitz", "description": "Every attack class, in rapid succession.",
              "mix": [{"attack": {"attack_id": a, "intensity": 0.6}, "weight": 1} for a in (
                  "channel.dephase", "channel.pauli_frame", "unauthorized.key_harvest_mitm", "forgery.blind",
                  "impersonation.keyless", "replay.resubmit", "unauthorized.non_recipient", "repudiation.inconsistent_keys")]},
    "insider_threat": {"name": "Insider threat", "description": "A rogue recipient and a rogue signer.",
                       "mix": [{"attack": {"attack_id": "forgery.insider"}, "weight": 2},
                               {"attack": {"attack_id": "impersonation.identity_swap"}, "weight": 1}]},
    "replay_storm": {"name": "Replay storm", "description": "Captured signatures thrown back at the network.",
                     "mix": [{"attack": {"attack_id": "replay.resubmit"}, "weight": 2},
                             {"attack": {"attack_id": "replay.forward_replay"}, "weight": 1},
                             {"attack": {"attack_id": "replay.delayed"}, "weight": 1}]},
}


def _money() -> str:
    cents = 100 + secrets.randbelow(2_500_000)
    return f"{cents / 100:,.2f}"


class TrafficController:
    def __init__(self, engine, hub, settings, executor) -> None:
        self.engine = engine
        self.hub = hub
        self.settings = settings
        self.executor = executor
        self.running = False
        self.user_stopped = False
        self.paused_idle = False
        self.rate_per_min = settings.traffic_rate_per_min
        self.generated = 0
        self.started_at: Optional[float] = None
        self.last_session_at: Optional[float] = None
        self.groups: Optional[list] = None
        self.errors = 0
        self._rr = 0
        self.blocked: dict = {}
        self._wake = asyncio.Event()

    def state(self) -> dict:
        return {"running": self.running, "paused_idle": self.paused_idle, "rate_per_min": self.rate_per_min,
                "generated": self.generated, "started_at": self.started_at, "last_session_at": self.last_session_at,
                "groups": self.groups, "errors": self.errors, "autostart": self.settings.autostart_traffic,
                "blocked": self.blocked}

    def _publish(self) -> None:
        self.hub.publish("traffic", "traffic.state", self.state())

    def start(self, rate_per_min: int | None = None, groups: list | None = None) -> dict:
        if rate_per_min:
            self.rate_per_min = max(1, min(120, int(rate_per_min)))
        if groups is not None:
            self.groups = groups or None
        if not self.running:
            self.started_at = time.time()
        self.running = True
        self.user_stopped = False
        self.paused_idle = False
        self._wake.set()
        self._publish()
        return self.state()

    def stop(self) -> dict:
        self.running = False
        self.user_stopped = True
        self._publish()
        return self.state()

    def on_clients(self, count: int) -> None:
        if count > 0 and self.settings.autostart_traffic and not self.user_stopped and not self.running:
            self.start()
        if count > 0 and self.paused_idle:
            self.paused_idle = False
            self._wake.set()
            self._publish()

    def _groups(self) -> list:
        gs = [g for g in self.engine.world.groups.values() if not g.hidden]
        if self.groups:
            gs = [g for g in gs if g.group_id in self.groups]
        return gs

    async def loop(self, stop: asyncio.Event) -> None:
        loop = asyncio.get_running_loop()
        while not stop.is_set():
            if self.running and self.hub.client_count == 0 and \
                    time.time() - self.hub.last_disconnect_at > self.settings.idle_pause_s and not self.paused_idle:
                self.paused_idle = True
                self._publish()
            if not self.running or self.paused_idle:
                self._wake.clear()
                try:
                    await asyncio.wait_for(self._wake.wait(), timeout=1.0)
                except asyncio.TimeoutError:
                    pass
                continue
            blocked = {r["group_id"]: r["blocked_reason"] for r in self.engine.reservoir() if r["blocked_reason"]}
            if blocked != self.blocked:
                for gid, why in blocked.items():
                    if self.blocked.get(gid) != why:
                        self.hub.publish("system", "system.notice", {"level": "info", "message": f"traffic pauses {gid}: {why}"})
                self.blocked = blocked
                self._publish()
            gs = [g for g in self._groups() if g.group_id not in blocked]
            if gs:
                g = gs[self._rr % len(gs)]
                self._rr += 1
                seq = self.generated + 1
                msg = (f"TX {seq:06d} | {g.signer_id}→{g.recipients[0]} | {_money()} QVC | "
                       f"ref {secrets.token_hex(4)}")
                try:
                    await loop.run_in_executor(self.executor, lambda: self.engine.sign_and_verify(
                        g.group_id, msg, origin="TRAFFIC", auto_distribute=True))
                    self.generated += 1
                    self.last_session_at = time.time()
                except Exception as exc:
                    self.errors += 1
                    self.hub.publish("system", "system.notice", {"level": "warning",
                                                                 "message": f"traffic {g.group_id}: {getattr(exc, 'message', exc)}"})
            period = 60.0 / max(1, self.rate_per_min)
            jitter = period * 0.2 * (secrets.randbelow(2001) / 1000.0 - 1.0)
            self._wake.clear()
            try:
                await asyncio.wait_for(stop.wait(), timeout=max(0.2, period + jitter))
            except asyncio.TimeoutError:
                pass


class CampaignRunner:
    def __init__(self, engine, hub, executor) -> None:
        self.engine = engine
        self.hub = hub
        self.executor = executor
        self.campaigns: dict = {}
        self.tasks: dict = {}

    def list(self) -> list:
        return sorted(self.campaigns.values(), key=lambda c: c["started_at"], reverse=True)

    def start(self, name: str, mix: list, rate_per_min: float, duration_s: float, group_ids: list | None = None,
              preset: str | None = None) -> dict:
        for m in mix:
            catalog_entry(m["attack"]["attack_id"])
        cid = str(uuid.uuid4())
        c = {"id": cid, "name": name, "preset": preset, "mix": mix, "rate_per_min": float(rate_per_min),
             "duration_s": float(duration_s), "group_ids": group_ids or ["g-alice"], "started_at": time.time(),
             "status": "RUNNING", "runs": 0, "detected": 0, "correct": 0, "last": None}
        self.campaigns[cid] = c
        self.tasks[cid] = asyncio.get_running_loop().create_task(self._run(cid))
        self.hub.publish("traffic", "campaign.state", c)
        return c

    def stop(self, cid: str) -> Optional[dict]:
        c = self.campaigns.get(cid)
        if not c:
            return None
        if c["status"] == "RUNNING":
            c["status"] = "STOPPED"
        t = self.tasks.pop(cid, None)
        if t:
            t.cancel()
        self.hub.publish("traffic", "campaign.state", c)
        return c

    async def _run(self, cid: str) -> None:
        loop = asyncio.get_running_loop()
        c = self.campaigns[cid]
        weights = [max(0.0, float(m.get("weight", 1))) for m in c["mix"]]
        total = sum(weights) or 1.0
        try:
            while c["status"] == "RUNNING" and time.time() - c["started_at"] < c["duration_s"]:
                r = secrets.randbelow(10_000) / 10_000 * total
                acc = 0.0
                pick = c["mix"][-1]
                for m, w in zip(c["mix"], weights):
                    acc += w
                    if r < acc:
                        pick = m
                        break
                group = c["group_ids"][c["runs"] % len(c["group_ids"])]
                try:
                    rep = await loop.run_in_executor(self.executor, lambda: self.engine.run_attack(
                        dict(pick["attack"]), group_id=group, counterfactual=False, origin="CAMPAIGN"))
                    c["runs"] += 1
                    c["detected"] += int(rep["detected"])
                    c["correct"] += int(rep["correctly_classified"])
                    c["last"] = {"attack_id": pick["attack"]["attack_id"], "detected": rep["detected"],
                                 "category": rep["detected_category"], "at": time.time()}
                except Exception as exc:
                    c["last"] = {"attack_id": pick["attack"]["attack_id"], "error": str(getattr(exc, "message", exc)), "at": time.time()}
                self.hub.publish("traffic", "campaign.state", c)
                await asyncio.sleep(60.0 / max(0.1, c["rate_per_min"]))
            if c["status"] == "RUNNING":
                c["status"] = "COMPLETED"
        except asyncio.CancelledError:
            pass
        finally:
            self.hub.publish("traffic", "campaign.state", c)


class Workers:
    def __init__(self, ctx) -> None:
        self.ctx = ctx
        self.stop = asyncio.Event()
        self.tasks: list = []
        self.reservoir_primed: set = set()

    def start(self) -> None:
        loop = asyncio.get_running_loop()
        s = self.ctx.settings
        self.tasks = [
            loop.create_task(self.ctx.traffic.loop(self.stop), name="traffic"),
            loop.create_task(self._reservoir(), name="reservoir"),
            loop.create_task(self._blocks(s.block_max_txs, s.block_max_age_s), name="blocks"),
            loop.create_task(self._metrics(), name="metrics"),
            loop.create_task(self._prune(), name="prune"),
        ]

    async def shutdown(self) -> None:
        self.stop.set()
        for c in list(self.ctx.campaigns.campaigns):
            self.ctx.campaigns.stop(c)
        for t in self.tasks:
            t.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def _sleep(self, s: float) -> bool:
        try:
            await asyncio.wait_for(self.stop.wait(), timeout=s)
            return True
        except asyncio.TimeoutError:
            return False

    async def _reservoir(self) -> None:
        loop = asyncio.get_running_loop()
        eng = self.ctx.engine
        if eng.stale_links():
            await loop.run_in_executor(self.ctx.executor, lambda: eng.calibrate(eng.stale_links()))
        while not self.stop.is_set():
            try:
                for r in eng.reservoir():
                    if r["blocked_reason"] or r["active"] >= r["target"]:
                        continue
                    if not (self.ctx.traffic.running and not self.ctx.traffic.paused_idle) and r["group_id"] in self.reservoir_primed:
                        continue
                    await loop.run_in_executor(self.ctx.executor, lambda gid=r["group_id"]: eng.distribute(gid, origin="RESERVOIR"))
                    if eng.reservoir_active(r["group_id"]) >= r["target"]:
                        self.reservoir_primed.add(r["group_id"])
                    break  # one distribution per tick keeps the API responsive
            except Exception as exc:  # pragma: no cover - logged, loop continues
                log.warning("reservoir: %s", exc)
            if await self._sleep(1.0):
                return

    async def _blocks(self, max_txs: int, max_age: float) -> None:
        while not self.stop.is_set():
            try:
                self.ctx.ledger.maybe_seal(max_txs, max_age)
            except Exception as exc:  # pragma: no cover
                log.warning("block producer: %s", exc)
            if await self._sleep(1.0):
                return

    async def _metrics(self) -> None:
        while not self.stop.is_set():
            if self.ctx.hub.client_count:
                try:
                    self.ctx.hub.publish("metrics", "metrics.tick", self.ctx.metrics.tick())
                except Exception as exc:  # pragma: no cover
                    log.warning("metrics tick: %s", exc)
            if await self._sleep(1.0):
                return

    async def _prune(self) -> None:
        while not self.stop.is_set():
            if await self._sleep(600.0):
                return
            try:
                self.ctx.prune()
            except Exception as exc:  # pragma: no cover
                log.warning("prune: %s", exc)
