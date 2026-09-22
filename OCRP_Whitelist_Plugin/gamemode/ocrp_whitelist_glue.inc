/*
 * Include this AFTER your normal includes.
 *
 * Then add the public callback below to your gamemode. If your gamemode
 * already has OnRconCommand, merge the OCRP line into that callback.
 */

stock OCRP_Whitelist_Rcon(const command[])
{
    return OCRP_HandleRconCommand(command);
}
