/* Example integration - merge these into your existing gamemode. */

public OnGameModeInit()
{
    print("[OCRP] Whitelist plugin integration loaded.");
    return 1;
}

public OnRconCommand(cmd[])
{
    if (OCRP_HandleRconCommand(cmd))
        return 1;

    return 0; // keep your existing RCON handling here
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
