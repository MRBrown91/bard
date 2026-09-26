# Testing

## Test layers

### Unit tests

Pure domain and application logic. No database, network, LLM, or STT provider.

### Integration tests

Database repositories and migrations against PostgreSQL. These are allowed to
use a disposable local database.

### API tests

FastAPI endpoints and WebSocket protocol behavior. External providers are
mocked behind interfaces.

### End-to-end tests

Reserved for a small number of critical workflows once the application has
multiple real components.

## Test requirements

- Reproduce bugs with a regression test where practical.
- Test authorization boundaries.
- Test campaign isolation.
- Test knowledge visibility before context construction.
- Test soft deletion and semantic invalidation separately.
- Do not test implementation details when behavior can be tested instead.
