# Goals

## Product goal

Build a context-aware Dungeon Master assistant that helps a DM surface relevant
campaign knowledge during a live D&D session.

A spoken or typed mention such as "LarkFellow" should allow the application to
identify the campaign entity and return useful, visibility-safe information.

## Architectural goals

- Support multiple users with isolated campaign data.
- Support multiple campaigns per user.
- Preserve campaign knowledge as structured, provenance-bearing data.
- Support documents and transcripts as source material.
- Support manual correction of extracted knowledge.
- Support live text streams over WebSockets.
- Leave clear extension points for STT, diarization, voice characteristics,
  RAG, embeddings, and live state changes.
- Keep the initial system inexpensive and operationally simple.
- Make the backend usable independently of the eventual Android client.

## Explicit non-goals for the first phase

- Fully autonomous DMing.
- LLM-generated canonical campaign state without review.
- Custom authentication.
- A graph database.
- Distributed job infrastructure.
- Kubernetes.
- Production-grade diarization or voice cloning.
