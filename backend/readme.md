# Telecom Forensics Backend

The desktop GUI authenticates against application users in PostgreSQL. The
database username and password are not desktop application credentials, and
the software does not ship a default application account.

## Start with Docker Compose

From the project root:

```bash
cd backend
cp -n .env.example .env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"
chmod 600 .env
```

Paste the generated value after `SECRET_KEY=` in `.env`, then run:

```bash
docker compose up -d --build
docker compose ps
```

Open the desktop GUI and select **First-time Setup**. The backend allows this
operation only while the user table is empty and always creates an admin role.

## Password recovery

Issue a private, short-lived reset token inside the running backend container:

```bash
docker compose exec api python -m app.cli reset-token USERNAME
```

Paste the token into **Forgot Password?** in the desktop login window. The
public forgot-password endpoint never returns a token or account details.

For an administrator working directly on the backend host, these commands are
also available:

```bash
python -m app.cli create-admin USERNAME
python -m app.cli reset-token USERNAME
python -m app.cli reset-password USERNAME
```
