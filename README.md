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
docker-compose exec web python manage.py migrate
```
Create a superuser (optional):
```bash
docker-compose exec web python manage.py createsuperuser
```

### 5. Generate static files
```bash
docker-compose exec web python manage.py collectstatic
```

### 6. Work with Django
All commands should be executed inside the web container. Examples:
```bash
docker compose exec web python manage.py shell
docker compose exec web python manage.py makemigrations
docker compose exec web pytest -v 
```

### 7. Stop containers
```bash
docker compose down
```
---

## 🚀 Stack
- Django, REST, Channels  
- PostgreSQL  
- Docker  
- GitFlow  
- Sphinx  

---

## 📌 Status
Early development stage.  
See [ROADMAP.md](./ROADMAP.md) for the roadmap.  

---

## ⚖️ License
No license yet. **All rights reserved by the authors.**
