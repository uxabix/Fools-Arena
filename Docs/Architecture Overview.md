# "Durak" Project Architecture Overview


```
        ┌────────────────┐
        │   Browser / JS │
        └───────┬────────┘
                │
┌───────────────┴───────────────┐
│        Django Templates       │
│ (HTML skeleton for pages)     │
│   - /fools/                   │
│   - /fools/lobbies/<id>/      │
│   - /accounts/...             │
└───────────────┬───────────────┘
                │
                ▼
┌────────────────────────────────┐
│        JavaScript Logic        │
│ - Fetch data from REST API     │
│ - Update DOM dynamically       │
│ - Connect to WebSocket         │
└───────────────┬────────────────┘
                │
  ┌─────────────┴──────────────┐
  │       REST API (JSON)      │
  │  - /api/accounts/          │
  │  - /api/fools/lobbies/     │
  │  - /api/fools/games/<id>/  │
  │  - /api/chat/...           │
  └─────────────┬──────────────┘
                │
                ▼
┌────────────────────────────────┐
│         Django Backend         │
│  - Models & Serializers        │
│  - Views / ViewSets            │
│  - Services / Game Logic       │
└─────────────┬─────────────┬────┘
              │             │
              ▼             ▼
    ┌─────────────┐   ┌─────────────────┐
    │  Database   │   │  WebSocket      │
    │  PostgreSQL │   │  Django Channels│
    └─────────────┘   │  /ws/games/...  │
                      │  /ws/lobbies/.. │
                      │  /ws/chat/...   │
                      └─────────────────┘
                      
```
### 🔹 How to Read the Diagram

1. **Browser / JS** → executes user actions.  
2. **Templates** → return HTML skeleton for pages.  
3. **JavaScript** → fetches data via REST API and subscribes to WebSocket for real-time updates.  
4. **REST API** → provides JSON data (games, players, moves, chat).  
5. **Django Backend** → contains business logic, models, serializers, WebSocket event handling.  
6. **Database** → stores users, games, moves, and messages.  
7. **WebSocket (Channels)** → delivers instant updates to all clients in a room.

---

### 🔹 Key Notes
- REST API and WebSocket **complement each other**: REST for initialization and stable data, WebSocket for real-time updates.  
- JS in templates can fully manage the DOM, templates only provide the page skeleton.  
- Modular app structure facilitates future SPA (React/Vue) integration.
