# OCRP Whitelist Plugin + Discord V6 Integration

This package adds a persistent SA-MP whitelist database and Pawn natives for OCRP.

## Architecture

Discord OCRP BOT V6 -> SA-MP RCON -> `OnRconCommand` glue -> `OCRP_WhitelistHandleRcon` -> `scriptfiles/ocrp_whitelist.txt`

The plugin does **not** contain the Discord bot token. The token remains in the bot's `.env` file.

## Important

The included Linux binary is built for **32-bit Linux/i386**, which is the architecture used by the classic SA-MP 0.3.7 Linux server. This workspace may not have a 32-bit linker installed, so the repository includes a GitHub Actions build that produces `ocrp_whitelist.so` automatically.
