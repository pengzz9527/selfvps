---
title: "Self-Host Cheatsheet"
description: "Docker, Nginx, Linux, SSL, and systemd commands — the only cheatsheet you need for VPS self-hosting"
date: 2026-05-16T10:00:00+08:00
slug: "cheatsheet"
---

## Docker

```bash
# --- Container Lifecycle ---
docker ps                      # List running containers
docker ps -a                   # List all containers (including stopped)
docker start <container>       # Start a stopped container
docker stop <container>        # Gracefully stop a container
docker restart <container>     # Restart a container
docker rm <container>          # Remove a stopped container
docker rm -f <container>       # Force remove a running container

# --- Images ---
docker images                  # List downloaded images
docker pull <image>:<tag>      # Pull an image (e.g., n8nio/n8n:latest)
docker rmi <image>             # Remove an image
docker build -t <name>:<tag> . # Build an image from Dockerfile
docker system prune -a         # Remove all unused images, containers, networks

# --- Logs & Debug ---
docker logs <container>        # View logs
docker logs -f <container>     # Follow log output (tail -f)
docker logs --tail 100 <cont>  # Show last 100 lines
docker exec -it <cont> /bin/sh # Enter a container shell (sh)
docker exec -it <cont> bash    # Enter a container shell (bash, if available)
docker inspect <cont>          # Show detailed container info (JSON)

# --- Compose ---
docker compose up -d           # Start services in background
docker compose down            # Stop and remove containers
docker compose down -v         # Also remove volumes (⚠️ destroys data)
docker compose logs -f         # Follow logs of all services
docker compose pull            # Pull latest images for all services
docker compose restart         # Restart all services
docker compose ps              # List compose project containers

# --- Volumes & Networks ---
docker volume ls               # List volumes
docker volume prune            # Remove unused volumes
docker network ls              # List networks
docker network create <name>   # Create a custom network
```

## Nginx

```bash
# --- Basic Commands ---
nginx -t                       # Test configuration for syntax errors
nginx -s reload                # Reload config without downtime
nginx -s stop                  # Force stop
nginx -s quit                  # Graceful stop (finish current requests)
systemctl restart nginx        # Restart via systemd
systemctl status nginx         # Check status
journalctl -u nginx --no-pager # View nginx service logs

# --- Common Locations ---
/etc/nginx/nginx.conf          # Main config file
/etc/nginx/sites-available/    # Site configs (enabled via symlink)
/etc/nginx/sites-enabled/      # Active site configs
/etc/nginx/conf.d/             # Additional config fragments
/var/log/nginx/access.log      # Access log
/var/log/nginx/error.log       # Error log
/var/www/html/                 # Default web root
```

```nginx
# --- Reverse Proxy Template ---
server {
    listen 80;
    server_name example.com;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

```nginx
# --- SSL with Let's Encrypt ---
server {
    listen 443 ssl;
    server_name example.com;

    ssl_certificate     /etc/letsencrypt/live/example.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/example.com/privkey.pem;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        # ... websocket support for apps like n8n
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}

server {
    listen 80;
    server_name example.com;
    return 301 https://$server_name$request_uri;  # HTTP → HTTPS redirect
}
```

```bash
# --- Certbot ---
certbot --nginx -d example.com          # Get SSL cert + auto-configure nginx
certbot renew                           # Renew all certificates
certbot renew --dry-run                 # Test renewal without actually renewing
certbot certificates                    # List all certificates
```

## Linux (Ubuntu/Debian)

```bash
# --- System Info ---
uname -a                    # Full system info
cat /etc/os-release         # OS version
hostnamectl                 # System hostname + OS details
free -h                     # Memory usage (human-readable)
df -h                       # Disk usage
du -sh *                    # Directory sizes in current folder
uptime                      # How long the system has been running
top / htop                  # Process monitor
lscpu                       # CPU info

# --- File Operations ---
ls -lah                     # List files with sizes + permissions
cp -r <src> <dst>           # Copy recursively
mv <src> <dst>              # Move/rename
rm -rf <dir>                # Remove directory and contents (⚠️ careful)
find / -name "filename"     # Find a file by name
grep -r "pattern" /path     # Recursively search for text
wc -l <file>                # Count lines in a file

# --- Permissions ---
chmod 755 <file>            # rwxr-xr-x (owner rwx, group+other rx)
chmod 600 <file>            # rw------- (owner only)
chown user:group <file>     # Change owner and group
chown -R user:group <dir>   # Recursive ownership change

# --- Processes ---
ps aux                      # List all running processes
ps aux | grep <name>        # Find a specific process
kill <PID>                  # Kill by process ID
kill -9 <PID>               # Force kill
pkill <name>                # Kill by name
nohup <command> &           # Run in background, survive logout

# --- Network ---
ss -tlnp                    # List listening TCP ports with processes
ss -tulpn                   # List all listening ports (TCP + UDP)
curl -I https://example.com # Show HTTP response headers
curl -s ifconfig.me         # Get public IP
ping -c 4 <host>            # Test connectivity
dig <domain>                # DNS lookup
mtr <host>                  # Network diagnostic (traceroute + ping)
```

## systemd

```bash
# --- Service Management ---
systemctl start <service>       # Start a service
systemctl stop <service>        # Stop a service
systemctl restart <service>     # Restart a service
systemctl enable <service>      # Enable auto-start on boot
systemctl disable <service>     # Disable auto-start
systemctl status <service>      # Check status + recent logs
systemctl daemon-reload         # Reload unit files after editing

# --- Journald Logs ---
journalctl -u <service>         # View logs for a service
journalctl -u <service> -f      # Follow logs (tail -f)
journalctl -u <service> --no-pager | tail -50  # Last 50 lines
```

## SSL / Certificates

```bash
# --- Quick SSL Check ---
openssl s_client -connect example.com:443 -servername example.com </dev/null 2>/dev/null | openssl x509 -noout -dates
# Shows cert issue and expiry dates

# --- Generate a Self-Signed Cert (for testing) ---
openssl req -x509 -nodes -days 365 -newkey rsa:2048 \
  -keyout /etc/ssl/private/selfsigned.key \
  -out /etc/ssl/certs/selfsigned.crt

# --- Check Cert Expiry Remotely ---
echo | openssl s_client -connect example.com:443 -servername example.com 2>/dev/null | openssl x509 -noout -enddate
```

## Quick References

| Topic | Command |
|-------|---------|
| Reload nginx config | `nginx -s reload` |
| Check nginx config | `nginx -t` |
| Restart Docker service | `systemctl restart docker` |
| View port usage | `ss -tulpn \| grep :PORT` |
| Disk usage by directory | `du -sh /path/to/dir` |
| Find largest files | `find / -type f -size +100M -exec ls -lh {} \;` |
| Latest kernel logs | `dmesg \| tail -20` |
| Firewall rules | `ufw status verbose` |
