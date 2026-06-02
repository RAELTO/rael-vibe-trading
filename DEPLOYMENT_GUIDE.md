# Guia de despliegue - Vibe Trading

Esta guia resume el despliegue realizado para el orquestador/backend en VPS y el frontend en Vercel.

## Arquitectura desplegada

- Frontend: Vercel, proyecto Vite en `dashboard`.
- Backend/orquestador: VPS Ubuntu Server 24 LTS.
- Servicio backend: `systemd` con nombre `vibe-trading.service`.
- Proxy publico: Website Management del proveedor hacia Nginx.
- API publica: `<BACKEND_PUBLIC_URL>`.
- Dashboard publico: `<FRONTEND_PUBLIC_URL>`.

## Datos del VPS

- Proveedor: `<VPS_PROVIDER>`.
- Usuario SSH: `<VPS_SSH_USER>`.
- IP compartida/publica: `<VPS_PUBLIC_IP>`.
- Puerto SSH publico: `<VPS_SSH_PORT>`.
- Host interno: `<VPS_INTERNAL_IP>`.
- Sistema operativo: Ubuntu Server 24 LTS 64-bit.

No guardar IPs, puertos SSH, usuarios ni URLs temporales reales en repositorios publicos. Mantener esos datos en notas privadas o en el panel del proveedor.

## Entrar al VPS desde Windows despues de reiniciar el PC

Abrir CMD o PowerShell y ejecutar:

```powershell
ssh <VPS_SSH_USER>@<VPS_PUBLIC_IP> -p <VPS_SSH_PORT>
```

Luego elevar a root:

```bash
sudo -i
```

Ir al proyecto:

```bash
cd /opt/rael-vibe-trading
```

El entorno virtual solo es necesario para comandos manuales de Python:

```bash
source venv/bin/activate
```

El servicio `systemd` no necesita que la terminal quede abierta.

## Instalacion base realizada en el VPS

```bash
apt update && apt upgrade -y
apt install -y git python3 python3-venv python3-pip nginx certbot python3-certbot-nginx ufw
reboot
```

Despues del reinicio:

```bash
ssh <VPS_SSH_USER>@<VPS_PUBLIC_IP> -p <VPS_SSH_PORT>
sudo -i
```

## Clonar proyecto

```bash
cd /opt
git clone --recurse-submodules https://github.com/RAELTO/rael-vibe-trading.git
cd /opt/rael-vibe-trading
```

## Entorno Python

```bash
python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## Archivo `.env`

Crear el `.env` en el VPS:

```bash
nano .env
```

Pegar las variables reales locales. No subir `.env` a GitHub.

Variables criticas para produccion:

```env
API_HOST=0.0.0.0
API_PORT=8000
TRADING_MODE=FUTURES
DECISION_MODE=DEEPSEEK_SINGLE
ANALYSIS_INTERVAL_SECONDS=900
TRADING_HOURS_ENABLED=true
TRADING_HOURS_START=8
TRADING_HOURS_END=20
TRADING_TIMEZONE=UTC
NEWS_INTERVAL_SECONDS=10800
CORS_ORIGINS=<FRONTEND_PUBLIC_URL>
```

Para guardar en nano:

```txt
Ctrl + O
Enter
Ctrl + X
```

Validar solo nombres de variables sin mostrar secretos:

```bash
grep -E '^[A-Z0-9_]+=' .env | cut -d= -f1
```

## Prueba manual del orquestador

```bash
cd /opt/rael-vibe-trading
source venv/bin/activate
python core/orchestrator.py
```

Debe mostrar algo como:

```txt
API en http://0.0.0.0:8000
```

Detener prueba manual:

```txt
Ctrl + C
```

## Servicio systemd

Archivo:

```bash
nano /etc/systemd/system/vibe-trading.service
```

Contenido:

```ini
[Unit]
Description=Vibe Trading Orchestrator
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/rael-vibe-trading
Environment="PYTHONUNBUFFERED=1"
ExecStart=/opt/rael-vibe-trading/venv/bin/python /opt/rael-vibe-trading/core/orchestrator.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Activar:

```bash
systemctl daemon-reload
systemctl enable vibe-trading
systemctl start vibe-trading
systemctl status vibe-trading
```

Debe verse:

```txt
Active: active (running)
```

Logs:

```bash
journalctl -u vibe-trading -f
```

Salir de `systemctl status` o `journalctl`:

```txt
q
```

Reiniciar servicio:

```bash
systemctl restart vibe-trading
```

## Nginx

Archivo:

```bash
nano /etc/nginx/sites-available/vibe-trading
```

Config:

```nginx
server {
    listen 80 default_server;
    server_name _;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /ws {
        proxy_pass http://127.0.0.1:8000/ws;
        proxy_http_version 1.1;

        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
    }
}
```

Activar sitio:

```bash
ln -s /etc/nginx/sites-available/vibe-trading /etc/nginx/sites-enabled/
unlink /etc/nginx/sites-enabled/default
nginx -t
systemctl reload nginx
```

Prueba local del VPS:

```bash
curl http://127.0.0.1/health
```

## Firewall

```bash
ufw allow <VPS_SSH_PORT>/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
ufw status
```

## Website Management en el proveedor

Como la IP es compartida, el puerto 80 publico directo de `<VPS_PUBLIC_IP>` puede no apuntar necesariamente al VPS. Por eso se uso Website Management.

Configuracion usada:

- Dominio falso: `<BACKEND_FAKE_DOMAIN>`.
- Temporary URL habilitada.
- IP interna: `<VPS_INTERNAL_IP>`.
- Port: `80`.
- URL temporal resultante: `<BACKEND_PUBLIC_URL>`.

Prueba publica:

```txt
<BACKEND_PUBLIC_URL>/health
```

## Frontend en Vercel

Repositorio: `RAELTO/rael-vibe-trading`.

Configuracion:

```txt
Framework / Preset: Vite
Root Directory: dashboard
Install Command: npm install
Build Command: npm run build
Output Directory: dist
```

Variables de entorno:

```env
VITE_API_URL=<BACKEND_PUBLIC_URL>
VITE_WS_URL=<BACKEND_PUBLIC_WS_URL>
```

Despues de cambiar variables o recibir un nuevo commit, redeploy en Vercel si no lo hace automaticamente.

## Actualizar el VPS despues de subir cambios a GitHub

Desde CMD/PowerShell:

```powershell
ssh <VPS_SSH_USER>@<VPS_PUBLIC_IP> -p <VPS_SSH_PORT>
```

En el VPS:

```bash
sudo -i
cd /opt/rael-vibe-trading
git pull origin main
systemctl restart vibe-trading
systemctl status vibe-trading
```

Ver logs si hace falta:

```bash
journalctl -u vibe-trading -f
```

## Verificaciones rapidas

Backend local dentro del VPS:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1/health
```

Backend publico:

```txt
<BACKEND_PUBLIC_URL>/health
<BACKEND_PUBLIC_URL>/state
```

Frontend:

```txt
<FRONTEND_PUBLIC_URL>
```

## Horario de trading

Configuracion actual:

```env
TRADING_HOURS_START=8
TRADING_HOURS_END=20
TRADING_TIMEZONE=UTC
```

Esto equivale en Colombia a:

```txt
03:00 a. m. - 03:00 p. m.
```

Si se quiere operar de 8 a. m. a 8 p. m. hora Colombia:

```env
TRADING_TIMEZONE=America/Bogota
TRADING_HOURS_START=8
TRADING_HOURS_END=20
```

Luego:

```bash
systemctl restart vibe-trading
```

## Binance y restricciones del VPS

El endpoint spot de Binance puede responder `451` por region restringida:

```bash
curl -i https://fapi.binance.com/fapi/v1/ping
```

Futures testnet funciono:

```bash
curl -i https://testnet.binancefuture.com/fapi/v1/ping
```

Se ajusto el proyecto para evitar inicializar spot en modo futures.

## Cancelacion del VPS

En el proveedor:

```txt
Virtual Servers -> vibe-trading-api -> Overview -> Stop Using -> Request Cancellation
```

Elegir:

```txt
Cancellation Type: End of Billing Cycle
Reason: Project ends
```

No elegir cancelacion inmediata si se quiere mantener el servidor hasta el fin del periodo pagado.
