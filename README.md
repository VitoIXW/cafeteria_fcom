# Bot del comedor US

Script en Python para leer el menú diario del comedor de la Universidad de Sevilla desde `https://sacu.us.es/menuSemanal?i=1` y enviarlo por Telegram. Está pensado para ejecutarse desde `cron` a las 07:00.

Ahora también puede mantener una lista local de suscriptores de Telegram para que el menú se envíe a varias personas.

## Qué he comprobado de la web

- La página publica un único bloque semanal en HTML estático.
- Hoy, 16/06/2026, el contenido publicado corresponde a `Menú semanal: 15/06/2026 - 19/06/2026`.
- Cada día aparece en una tabla con tres columnas: `Primer plato`, `Segundo plato` y `Postre`.

Eso permite sacar el menú sin navegador ni JavaScript.

## Uso local

```bash
cp .env.example .env
python3 comedor_bot.py --dry-run
python3 comedor_bot.py --date 2026-06-16 --dry-run
```

El script lee automáticamente un fichero `.env` en la raíz del proyecto. Un ejemplo está en [.env.example](/home/alfredo/repositorios/comedor/.env.example).

Para enviar a Telegram, rellena tu `.env`:

```bash
python3 comedor_bot.py
```

Variables opcionales:

- `COMEDOR_MENU_URL`: cambia la URL fuente.
- `COMEDOR_TARGET_DATE`: fecha objetivo en `YYYY-MM-DD`.
- `COMEDOR_ENV_FILE`: ruta de un fichero de variables alternativo.
- `COMEDOR_SUBSCRIBERS_FILE`: ruta del JSON de suscriptores.
- `COMEDOR_STATE_FILE`: ruta del JSON donde se guarda el último `update_id`.

## Suscripciones del bot

Antes de enviar el menú, el script consulta `getUpdates` de Telegram y procesa estos comandos:

- `/start`: activa al usuario y guarda `chat_id`, nombre, `username`, origen y estado
- `/stop`: deja al usuario marcado como inactivo

El fichero de suscriptores queda en `subscribers.json` por defecto, con una estructura parecida a esta:

```json
{
  "subscribers": [
    {
      "chat_id": "123456789",
      "name": "Tu Nombre",
      "username": "tuusuario",
      "active": true,
      "source": "telegram",
      "updated_at": "2026-06-16T14:00:00"
    }
  ]
}
```

Tu `TELEGRAM_CHAT_ID` del `.env` se mantiene como suscriptor activo por defecto, así que tú seguirás recibiendo el menú aunque nadie haya enviado `/start`.

Importante: como el bot se ejecuta con `cron`, las altas y bajas se procesan cuando corre el script. Si alguien envía `/start` a las 15:00, quedará registrado en la siguiente ejecución programada.

## Formato del mensaje

El mensaje se envía con formato HTML de Telegram:

- cabecera con fecha
- campus y semana
- bloques separados para primer plato, segundo plato y postre
- enlace a la fuente

En `--dry-run` el script imprime una vista legible en consola.

## Cron

Ejemplo de `crontab -e` para lanzarlo de lunes a viernes a las 07:00:

```cron
0 7 * * 1-5 cd /home/alfredo/repositorios/comedor && /usr/bin/python3 /home/alfredo/repositorios/comedor/comedor_bot.py >> /tmp/comedor_bot.log 2>&1
```

Si prefieres guardar el fichero en otra ruta:

```cron
0 7 * * 1-5 cd /home/alfredo/repositorios/comedor && /usr/bin/python3 /home/alfredo/repositorios/comedor/comedor_bot.py --env-file /ruta/privada/comedor.env >> /tmp/comedor_bot.log 2>&1
```

## Notas de robustez

- Si SACU no publica menú para la fecha consultada, el bot lo indica en vez de fallar.
- El parser está montado sobre la tabla HTML real que publica la web.
- Hay tests del parser, del `.env` y del registro de suscriptores en `tests/test_comedor_bot.py`.
