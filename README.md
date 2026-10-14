# 🃏 Fool's Arena Game

An online multiplayer version of the classic Russian card game **Durak**, built with **Django** and **Django Channels**.  

---
## Setup
### 1. Clone the repository
```bash
git clone https://github.com/uxabix/Django-Fools_Arena
cd Django-Fools_Arena
```
### 2. Configure environment variables
Copy .env.example to .env:
```bash
cp .env.example .env
```
### 3. Start the project
Run containers:
```bash
docker compose up --build
```
Available services:
- Django + Channels: http://localhost:8000
- PostgreSQL: localhost:5432

### 4. Apply migrations and create a superuser
Run migrations:
```bash
docker compose exec web python manage.py migrate
```
Create a superuser (optional):
```bash
docker compose exec web python manage.py createsuperuser
```

### 5. Generate static files
```bash
docker compose exec web python manage.py collectstatic
```

### 6. Work with Django
Run migrations, tests, and management commands **inside the `web` container** (after `docker compose up`):

```bash
docker compose exec web python manage.py migrate
docker compose exec web python manage.py makemigrations
docker compose exec web pytest -v
```

If containers are not running yet, you can use a one-off container (starts dependencies per Compose file):

```bash
docker compose run --rm web python manage.py migrate
docker compose run --rm web pytest -v
```

### Chat: API and templates
REST (session or token auth as configured for DRF):

- `GET /api/chat/chats/` — list chats for the current user  
- `POST /api/chat/chats/direct/` — JSON body `{ "other_user_id": "<uuid>" }` to open or reuse a 1:1 chat  
- `GET|POST /api/chat/chats/<chat_uuid>/messages/` — list recent messages or `{ "content": "..." }` to post  

Same behaviour in server-rendered UI (login required):

- `/chat/` — inbox  
- `/chat/direct/new/` — start a direct chat by username  
- `/chat/<chat_uuid>/` — history, HTTP post form, optional WebSocket client block on the page  

Blocking uses `accounts.Block`: the blocked user cannot send **direct** messages to the blocker; lobby chats are unchanged.

### 7. Stop containers
```bash
docker compose down
```
---

## Documentation

Developer documentation is built with [Sphinx](https://www.sphinx-doc.org/) from the [`docs/`](docs/) directory (autodoc, Google-style docstrings via Napoleon, viewcode).

Security limits, account rules, and server-side game checks are kept in [Docs/engineering-decisions.md](Docs/engineering-decisions.md). Update that file in the same change that alters one of those decisions.

**Install dependencies** (includes Sphinx):

```bash
pip install -r requirements.txt
```

**Generate HTML** (either command from the repository root):

```bash
cd docs && make html
```

```bash
sphinx-build -b html docs docs/_build
```

Open `docs/_build/html/index.html` in a browser.

**Rebuild after code or docstring changes** (clean output, then build again):

```bash
cd docs && make clean html
```

Or remove the build directory and run `sphinx-build` again:

```bash
rm -rf docs/_build && sphinx-build -b html docs docs/_build
```

**Using Docker** (from the project root, with the stack running and the app image built):

```bash
docker compose exec web sphinx-build -b html docs docs/_build
```

The `docs/_build/` directory is gitignored.

---

## 🚀 Stack
- Django, REST, Channels
- Redis
- PostgreSQL  
- Docker  
- GitFlow  
- Sphinx  

---

## 📌 Status
Early development stage.  
See [ROADMAP.md](./ROADMAP.md) for the roadmap.  

---

## Card artwork

The card faces and the red card back are SVG files from the Wikimedia Commons category [Public domain playing cards](https://commons.wikimedia.org/wiki/Category:Public_domain_playing_cards). They are dedicated to the public domain under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/). The faces were uploaded by [AustinGabriel64](https://commons.wikimedia.org/wiki/User:AustinGabriel64). The back is [Card back red.svg](https://commons.wikimedia.org/wiki/File:Card_back_red.svg), from a public-domain design by [Trocche100](https://commons.wikimedia.org/wiki/User:Trocche100). Copies are stored in `fools/static/fools/cards/`. The jokers from that set are not used.

## ⚖️ License
No license yet. **All rights reserved by the authors.** The card artwork above is an exception: those files are CC0.
