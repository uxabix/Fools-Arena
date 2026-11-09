# Project Structure Plan: "Durak" Card Game

## Overview
This Django project implements an online card game "Durak" with user profiles, game rooms, real-time gameplay, and chat functionality. The project uses **Django REST Framework** for API development, **Django templates** for temporary front-end rendering, and **WebSocket (Django Channels)** for real-time updates. The architecture is modular, maintainable, and ready for future SPA integration (React/Vue).

> Note: The structure below is a proposed plan. It may evolve or change over time according to the best development practices and project growth. The `Common / Utilities` application may not be necessary depending on project needs.

---

## 1. Applications

### 1️⃣ Accounts (`accounts`)
**Purpose:** User management, authentication, and profile system.

**Models:**
- `User` (custom `AbstractUser`)  
- `Profile` (OneToOne with User; stores rating, statistics, avatar)

**Views / URLs:**
- Templates:
  - `/accounts/login/` – login page  
  - `/accounts/register/` – registration page  
  - `/accounts/profile/` – personal profile  
  - `/accounts/profile/<id>/` – view other users’ profiles
- REST API:
  - `/api/accounts/` – list of users (for admin/testing)  
  - `/api/accounts/<id>/` – user details (statistics, rating)

**Responsibilities:**
- Registration, login/logout, profile viewing  
- API endpoints for user data for front-end consumption

---

### 2️⃣ Fools (`fools`)
**Purpose:** Core game logic, lobby management, and real-time gameplay.

**Models:**
- `Lobby` – game lobby (name, status, settings)  
- `Game` – game session (lobby, trump card, runtime state)  
- `GamePlayer` – relation User ↔ Game (seat, cards remaining)  
- `Card`, `CardSuit`, `CardRank` – card entities  
- `Turn`, `Move`, `TableCard` – game moves and table state

**Views / URLs:**
- Templates:
  - `/fools/` – list of open lobbies (HTML shell, JS pulls data)  
  - `/fools/lobbies/<lobby_id>/` – lobby page (players, chat, start game)  
  - `/fools/play/<game_id>/` – active table UI
- REST API:
  - `/api/fools/lobbies/` – list/create lobbies  
  - `/api/fools/lobbies/<id>/` – lobby details, join, leave, ready, start  
  - `/api/fools/games/<id>/` – current game state and moves (attack, defend, etc.)

**WebSocket:**
- `/ws/lobbies/<lobby_id>/` – lobby events (player ready, game started)  
- `/ws/games/<game_id>/` – real-time game events (player moves, card updates)

**Responsibilities:**
- Game mechanics implementation in `services.py`  
- Lobby creation/joining, game state management  
- WebSocket consumers for real-time gameplay

---

### 3️⃣ Chat (`chat`)
**Purpose:** Real-time communication between players in rooms.

**Models:**
- `Message` – chat messages (author, text, timestamp, room)

**Views / URLs:**
- REST API:
  - `/api/chat/rooms/<room_id>/messages/` – chat history  
  - `/api/chat/rooms/<room_id>/send/` – send a new message (POST)
- WebSocket:
  - `/ws/chat/<room_id>/` – real-time chat updates

**Responsibilities:**
- WebSocket consumer for chat messages  
- Optional AJAX fallback for REST API access to chat history  

---

### 4️⃣ Common / Utilities (`common`) (Optional)
**Purpose:** Shared utilities, helper functions, mixins, and validation logic.

**Responsibilities:**
- Reusable code across apps (validators, serializers, helper functions)  
- Base classes for models, views, or consumers

> May be omitted if not needed.

---

## 2. URL Organization

**Templates (HTML pages, JS loads data from API):**
/accounts/login/
/accounts/register/
/accounts/profile/
/accounts/profile/<id>/
/fools/
/fools/lobbies/<lobby_id>/
/fools/play/<game_id>/

**REST API (JSON data for front-end):**
/api/accounts/
/api/accounts/<id>/
/api/fools/lobbies/
/api/fools/lobbies/<id>/
/api/fools/games/<id>/
/api/chat/chats/
/api/chat/chats/<chat_id>/messages/

**WebSocket (real-time updates):**
/ws/lobbies/<lobby_id>/
/ws/games/<game_id>/
/ws/chat/<chat_id>/


---

## 3. Front-End Integration Approach

- Initial front-end uses **Django templates** with minimal JS.  
- JS requests data from REST API endpoints to render game state, player list, and chat messages.  
- WebSocket used for real-time updates (game moves, chat messages).  
- This approach allows **easy future migration to SPA** (React/Vue) without changes to the backend API or WebSocket logic.  

---

## 4. Team Responsibilities

| App        | Suggested Team Member Focus                  |
|------------|----------------------------------------------|
| `accounts` | Authentication, user profiles, API           |
| `fools`    | Core game logic, lobby management, WebSocket  |
| `chat`     | Chat logic, WebSocket, API endpoints         |
| `common`   | Shared utilities and helpers (optional)      |
