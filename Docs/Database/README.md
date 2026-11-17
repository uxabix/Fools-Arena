# Database diagram

`schema.png` in the repository root is generated from the Django models. The generator is [django-extensions](https://django-extensions.readthedocs.io/en/latest/graph_models.html) `graph_models`. Rendering uses `pydot` and the Graphviz `dot` binary. Both Python packages are in `requirements.txt`. The image installs Graphviz in `Dockerfile`.

The picture includes `accounts`, `chat`, and `fools` only. Django’s own tables are omitted with `-X`: `ContentType`, `Session`, `LogEntry`, `Permission`, and `Group`. `Permission` and `Group` still attach to `User` through `AbstractUser`, so they must stay in `-X` even though those apps are not listed. `--no-inheritance` hides `AbstractUser`, `AbstractBaseUser`, and `PermissionsMixin`, which are not tables. `--pydot` is required: without it the command looks for `pydotplus`, which this project does not install.

Run this from the repository root. The `web` service mounts the project at `/app`, so the file lands in the repository root.

```bash
docker compose run --rm web python manage.py graph_models accounts chat fools -X ContentType,Session,LogEntry,Permission,Group --no-inheritance --pydot -o schema.png
```

If the `web` container is already up, the same command works with `docker compose exec web` instead of `docker compose run --rm web`.

Rerun it after model changes. It overwrites `schema.png`.

`dbschema.puml` is a separate hand-drawn sketch. It is not the source of `schema.png`.
