# Django - Durak card game — Roadmap

## Technologies
- Django, Channels
- PostgreSQL
- Docker
- GitFlow
- Sphinx

## Documentation & Tests
- Documentation with Sphinx
- README with setup instructions
- Unit and integration tests throughout the development process

---

## v0.0 — Setup (infrastructure)
- [x] Initialize Django project
- [x] Create base app (`core`)
- [x] Connect PostgreSQL (`settings.py`)
- [x] Dockerfile for Django
- [x] docker-compose (Django + PostgreSQL)
- [x] Initialize Git repository, set up GitFlow
- [x] Configure CI (linter + tests on GitHub Actions)
- [x] Basic tests (server startup, endpoint availability)

---

## v0.1 — Users & Base models
- [x] Create models: `User`, `Card`, `Game` (draft)
- [x] Run migrations
- [x] Add admin panel for User/Game
- [x] Integrate Django Channels
- [x] Write a test WebSocket consumer (echo/ping)
- [x] Implement registration (Django/DRF)
- [x] Implement login (JWT or session-based)
- [x] Tests: user creation, login/logout, WebSocket connection

---

## v0.2 — Lobby system
- [x] Model `Lobby` (id, owner, players, status)
- [x] API: create lobby / join / leave
- [x] WebSocket: notify players when lobby state changes
- [] Main page (Django template SSR or API)
- [x] API: list of lobbies (filtering, search)
- [ ] API: friend search (by nickname/email)
- [ ] Model `Friendship` (user_from, user_to, status)
- [ ] Tests: lobby creation, joining, API queries, friendship

---

## v1.0 — MVP (1v1 game, basic rules)
- [x] Model `GameRound` (deck, current player, table)
- [x] Implement basic “Durak” rules (2 players)
- [x] Card dealing, trump suit selection
- [x] WebSocket: exchange game events (move → update all players)
- [x] API: start game from lobby
- [ ] Notifications (via WebSocket events + DB logging)
- [ ] Docker production config (gunicorn/daphne + nginx)
- [ ] Minimal deploy (Railway/Heroku/VPS)
- [ ] Tests: gameplay scenarios (deal cards, make a move, check winner)

---

## v1.1 — Lobby extensions
- [x] Lobby settings (number of players, private/public, password)
- [ ] Game invitations (via friend list / invite link)
- [ ] Extended rules (chasing, finish deck, auto-pass)
- [ ] WebSocket: invitation events
- [ ] Tests: private lobby, invitations

---

## v1.2 — Social features
- [ ] Lobby chat (WebSocket, history storage)
- [ ] Profile settings (avatar, status, bio)
- [ ] Improved notifications (e-mail for invites)
- [ ] Tests: chat, profile updates

---

## v1.3+ (optional)
- [ ] Player rating system
- [ ] Game history
- [ ] Mobile-friendly frontend
- [x] Support for 3–4 players

---

## Teamwork (3 backend devs)
Example task distribution for **v0.1**:
- **Dev1:** Models User/Game/Card + migrations + tests  
- **Dev2:** Channels + test WebSocket consumer  
- **Dev3:** Registration/login + API  

General rule: all tasks go through code review, roles may rotate.

---

## Kanban flow (for GitHub Projects)
- **To Do** — tasks from roadmap (not yet started)  
- **In Progress** — tasks currently being worked on  
- **Review** — pull requests waiting for review  
- **Done** — completed tasks  

---
