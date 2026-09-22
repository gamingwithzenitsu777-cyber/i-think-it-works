# Installation on Reviactyl / SA-MP Linux 0.3.7

1. Run the GitHub Action `Build OCRP Whitelist Plugin` and download its artifact `OCRP-Whitelist-Plugin`.
2. Extract `ocrp_whitelist.so` into the server's `plugins/` directory.
3. Extract `ocrp_whitelist.inc` into your Pawn include directory.
4. Add `ocrp_whitelist.so` to the existing `plugins` line in `server.cfg`.
5. Add the following to the gamemode (merge it with any existing callbacks):

```pawn
#include <ocrp_whitelist>

public OnRconCommand(cmd[])
{
    if (OCRP_HandleRconCommand(cmd))
        return 1;
    return 0;
}

public OnPlayerConnect(playerid)
{
    new name[MAX_PLAYER_NAME + 1];
    GetPlayerName(playerid, name, sizeof name);
    if (!OCRP_IsWhitelisted(name))
    {
        SendClientMessage(playerid, 0xFF5555FF, "[OCRP] You are not whitelisted. Apply in our Discord.");
        Kick(playerid);
        return 1;
    }
    return 1;
}
```

6. Restart the server.
7. Test the RCON command manually: `whitelist add John_Doe`.
8. In the Discord bot `.env`, set:

```env
SAMP_RCON_PASSWORD=YOUR_EXISTING_RCON_PASSWORD
SAMP_WHITELIST_COMMAND=whitelist add {name}
```

The bot can then use the same RCON path it already has in V6.

## Important

If your gamemode already has `OnPlayerConnect` or `OnRconCommand`, **do not create a second callback**. Merge the plugin checks into the existing callback.
