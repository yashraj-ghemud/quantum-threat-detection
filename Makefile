.PHONY: install dev start build test test-py test-web e2e openapi legacy clean
install:        ## Python + web dependencies
	pip install -r requirements.txt
	cd web && npm ci
dev:            ## backend (reload) + Vite dev server
	./scripts/dev.sh
start:          ## build UI if needed and serve everything on :8000
	./scripts/start.sh
build:          ## production web build
	cd web && npm run build
test: test-py test-web
test-py:        ## engine, protocol, detection, analysis and API tests
	PYTHONPATH=src:. python -m pytest tests/sentinel tests/server -q
test-web:       ## type-check + unit tests
	cd web && npm run check
e2e:            ## Playwright end-to-end (starts its own backend)
	cd web && npm run build && npx playwright test
openapi:        ## dump the OpenAPI document
	PYTHONPATH=src python -m server.dump_openapi docs/openapi.json
legacy:         ## the original v1 Streamlit dashboard (unchanged)
	streamlit run dashboard/app.py
clean:
	rm -rf web/dist data
