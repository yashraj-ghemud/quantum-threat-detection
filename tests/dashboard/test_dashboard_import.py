"""Tests for dashboard imports."""

def test_dashboard_imports():
    """Verify that dashboard components can be imported safely."""
    try:
        import dashboard.app
        import dashboard.components.metrics
        import dashboard.components.charts
        import dashboard.components.quantum_view
        import dashboard.components.attack_panel
        import dashboard.components.security_panel
    except ImportError as e:
        assert False, f"Dashboard import failed: {e}"
