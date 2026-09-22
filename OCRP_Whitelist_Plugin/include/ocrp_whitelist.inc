#if defined _ocrp_whitelist_included
    #endinput
#endif
#define _ocrp_whitelist_included

native bool:OCRP_IsWhitelisted(const name[]);
native bool:OCRP_AddWhitelist(const name[]);
native bool:OCRP_RemoveWhitelist(const name[]);
native OCRP_GetWhitelistCount();
native bool:OCRP_HandleRconCommand(const command[]);
native bool:OCRP_GetWhitelistName(index, name[], maxlen);

stock bool:OCRP_PlayerIsWhitelisted(playerid)
{
    new name[MAX_PLAYER_NAME + 1];
    GetPlayerName(playerid, name, sizeof name);
    return OCRP_IsWhitelisted(name);
}
