# Documentation

Comprehensive documentation for SciTrans-LLMs system architecture, features, configuration, and usage.

## Documentation Structure

### Core Documentation

#### `architecture.md`
System architecture and design principles.
- Component overview
- Data flow
- Architectural invariants
- Module dependencies

#### `phase_plan.md`
Development phases and completion criteria.
- Phase 0: Critical bugs
- Phase 1: Layout intelligence
- Phase 2: Math-safe segmentation
- Phase 3: Table detection
- Phase 4: Table handling
- Phase 5: Benchmarking

---

### Feature Documentation

#### `FEATURES.md`
Complete feature guide with examples.
- Math-safe translation
- Table handling
- Multi-column reading order
- Paragraph merging
- Adaptive scoring
- Caching and reranking

#### `ADAPTIVE_SCORING.md`
Detailed explanation of pre/post scoring system.
- Complexity factors (9 dimensions)
- Quality dimensions (5 dimensions)
- Adaptive parameter selection
- Automated decision-making

#### `CASCADE_FREE.md`
Cascade-free backend documentation.
- Multi-model ensemble approach
- Reranking strategy
- Zero-cost production quality

#### `RELATED_WORKS.md`
Comparison with existing systems.
- PDFMathTranslate
- DocuTranslate
- Commercial tools
- SciTrans innovations

---

### Backend Documentation

#### `BACKENDS.md`
Complete guide to all translation backends.
- Backend comparison table
- Setup instructions per backend
- API key configuration
- Performance characteristics

**Backends covered:**
- `cascade_free` (default, free)
- `anthropic` (Claude, paid)
- `openai` (GPT, paid)
- `google` (free, limited)
- `huggingface` (free/paid)
- `ollama` (local, free)
- `dummy` (testing only)

---

### Configuration and Deployment

#### `CONFIGURATION.md`
Configuration guide and security best practices.
- Environment variables
- API key management
- Output configuration
- Feature toggles
- Security best practices

#### `BENCHMARKS.md`
Benchmarking guide.
- Running benchmarks
- Interpreting results
- Visualization
- Adding custom PDFs

#### `TESTING.md`
Testing guide for developers.
- Running tests
- Writing new tests
- Coverage goals
- CI/CD integration

#### `PRODUCTION_READINESS_CHECKLIST.md`
Pre-deployment verification checklist.
- Repository hygiene
- Build verification
- Security audit
- Integration tests
- Documentation completeness

---

### Development Documentation

#### `PRODUCTION_ROADMAP.md`
Detailed roadmap for production deployment.
- Current capabilities
- Known limitations
- Future improvements
- Timeline estimates

#### `dev_notes/`
Development notes and baselines.
- `production_readiness_baseline.md` — Pre-hardening status

---

## Quick Navigation

**Getting started:**
- [`../README.md`](../README.md) — Project overview
- [`../QUICK_START.md`](../QUICK_START.md) — Quick reference
- [`../INSTALL.md`](../INSTALL.md) — Installation guide

**For users:**
- [`FEATURES.md`](FEATURES.md) — What can SciTrans do?
- [`BACKENDS.md`](BACKENDS.md) — Which backend should I use?
- [`CONFIGURATION.md`](CONFIGURATION.md) — How do I configure it?
- [`BENCHMARKS.md`](BENCHMARKS.md) — How good is the quality?

**For developers:**
- [`architecture.md`](architecture.md) — System design
- [`TESTING.md`](TESTING.md) — Running and writing tests
- [`../CONTRIBUTING.md`](../CONTRIBUTING.md) — Contribution guide
- [`phase_plan.md`](phase_plan.md) — Development phases

**For researchers:**
- [`ADAPTIVE_SCORING.md`](ADAPTIVE_SCORING.md) — Research contribution
- [`CASCADE_FREE.md`](CASCADE_FREE.md) — Novel backend approach
- [`RELATED_WORKS.md`](RELATED_WORKS.md) — Comparison with prior work
- [`../THESIS_RESEARCH.md`](THESIS_RESEARCH.md) — Thesis overview

**For production:**
- [`PRODUCTION_READINESS_CHECKLIST.md`](PRODUCTION_READINESS_CHECKLIST.md) — Deployment checklist
- [`PRODUCTION_ROADMAP.md`](PRODUCTION_ROADMAP.md) — Roadmap to production
- [`CONFIGURATION.md`](CONFIGURATION.md) — Security and config
- [`../SECURITY.md`](SECURITY.md) — Security policy

---

## Documentation Standards

### Writing Style
- Clear and concise
- Examples for every feature
- Code snippets with full commands
- Troubleshooting sections

### Structure
Each doc should have:
1. Purpose/overview
2. Usage examples
3. Configuration options
4. Troubleshooting
5. Contact/references

### Keeping Docs Current
- Update docs when features change
- Add examples for new features
- Mark deprecated features clearly
- Test all code examples

---

## Building Documentation

Currently, documentation is in Markdown. For future releases, consider:
- MkDocs for HTML docs
- Sphinx for API reference
- ReadTheDocs hosting

---

## Contributing to Docs

- Fix typos via pull request
- Add examples for unclear sections
- Report outdated information
- Suggest improvements

**Contact:** aknk.v@pm.me

---

## License

Documentation is licensed under MIT (same as code).

