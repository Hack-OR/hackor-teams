#!/usr/bin/env python3

import discord
import discord.ext.commands

import typing
import yaml
import json
import logging
import unicodedata
import time
import sys

import db
import teamutil

root = logging.getLogger()
root.setLevel(logging.DEBUG)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.DEBUG)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
root.addHandler(handler)
fh = logging.FileHandler('hackor-bot.log')
fh.setFormatter(formatter)
root.addHandler(fh)

_logger = logging.getLogger('discord')
_logger.setLevel(logging.WARNING)

_logger = logging.getLogger('asyncio')
_logger.setLevel(logging.WARNING)

intents = discord.Intents.default()
intents.reactions = True
intents.members = True
client = discord.ext.commands.Bot(command_prefix='!', intents=intents)

config = dict()
msg_settings = {'allowed_mentions': discord.AllowedMentions(everyone=False, roles=set())}

TESTING_MODE = False


##########


_user_cache = dict()
'''
resolves a username to a discord.member.Member object
'''
async def resolve_user(ctx: discord.ext.commands.context.Context, user: str, use_cache: bool=False) -> discord.member.Member:
    assert isinstance(user, str)

    converter = discord.ext.commands.MemberConverter() # XXX: should I move this to the global scope?
    member = _user_cache.get(user)
    if (not use_cache) or not member:
        try:
            member = await converter.convert(ctx, user)
        except discord.ext.commands.errors.MemberNotFound:
            member = None

        if (not member) and user.startswith('@'):
            member = await resolve_user(ctx, user[1:], use_cache=use_cache)

        if member:
            _user_cache[user] = member

    return member


'''
creates a set of discord.member.Member who are competitors
'''
async def get_competitors(ctx: discord.ext.commands.context.Context) -> typing.Set[discord.member.Member]:
    competitors = set(discord.utils.get(ctx.guild.roles, id=config['discord']['competitor-id']).members)
    return competitors


'''
get the db users dict for the Member object
'''
def _get_db_user_from_user(user: discord.member.Member) -> dict:
    uid = str(user)

    assert 'users' in db.db
    logging.debug('_get_db_user_from_user: fetching db user: %r' % uid)
    if uid not in db.db['users']:
        db.db['users'][uid] = dict()
        db.write()

    return db.db['users'][uid]


'''
get the db users dict for the user who executed a command based on ctx
'''
def _get_db_user_from_ctx(ctx: discord.ext.commands.context.Context) -> dict:
    assert ctx
    return _get_db_user_from_user(ctx.author)


'''
a hack to assign names to emojis so that we can use them in config files 
without needing to type unicode emojis
'''
def _emoji_to_name(emoji: str) -> str:
    return unicodedata.name(emoji).lower().replace(' ', '_').replace('symbol_letter_', '')


##########


@client.event
async def on_ready() -> None:
    logging.info(f'{client.user} has connected to Discord!')
    await client.change_presence(activity=discord.Activity(type=discord.ActivityType.listening, name='your requests'))


@client.event
async def on_raw_reaction_add(payload: discord.raw_models.RawReactionActionEvent) -> None:
    if payload.message_id == config['discord']['specializations']['message-id']:
        channel = await client.fetch_channel(payload.channel_id)
        message = await channel.fetch_message(payload.message_id)
        user = await client.fetch_user(payload.user_id)
        emoji = payload.emoji

        name = _emoji_to_name(emoji.name)
        try:
            tag = config['discord']['specializations']['emojis'].get(name)
            if not tag:
                logging.debug(f'Removing meaningless emoji "{name}" ({emoji.name})')
                await message.remove_reaction(emoji, payload.member)
        except Exception as e:
            logging.error('when adding reaction: ' + str(e))


##########


'''
strip backticks
'''
def _hack_san(data):
    return data.replace('`', '')


@client.command(pass_context=True)
async def request(ctx: discord.ext.commands.context.Context, *args) -> None:
    if ctx.channel.id == config['discord']['team-requests']['channel-id']:
        author_user = _get_db_user_from_ctx(ctx)
        if author_user.get('lock_team', False):
            await ctx.send('**Error:** Cannot request when a team is locked. Please unlock with `!unlock-team` if you\'d like. Your currently-locked team is: `' + ' '.join(list({str(ctx.author)} | set(_get_db_user_from_ctx(ctx).get('team_requests', [])))) + '`', **msg_settings)
            return False

        if config['discord']['competitor-id'] not in [x.id for x in ctx.author.roles]:
            await ctx.send('**Error:** Only competitors may use `!request`.', **msg_settings)
            return False

        _users_not_found = list()
        _users_unauthorized = list()
        _users_found = list()
        _requesting_self = False
        for username in set(args):
            # the work usually won't be wasted since it's stored in cache
            if not (user := await resolve_user(ctx, username)):
                _users_not_found.append(username)
            else:
                if str(user) == str(ctx.author):
                    _requesting_self = True
                    continue

                # check to make sure requested user has the right role
                if config['discord']['competitor-id'] not in [x.id for x in user.roles]:
                    _users_unauthorized.append(username)
                    continue
                
                _users_found.append(str(user))

        # don't do `if _users_found` because we want "!maketeams" (without args) to reset this
        author_user['team_requests'] = _users_found
        db.write()

        res_msg = 'Resetting your requested users...'
        if _users_found:
            res_msg = 'Setting your requested users to `' + ' '.join(_users_found) + '`...'

        if _requesting_self:
            await ctx.send('**Warning:** You requested yourself to be on your team. There\'s no need for this as I can guarantee you that you\'ll be on the same team as yourself! ' + res_msg, **msg_settings)

        if _users_unauthorized:
            # send message saying the users weren't found. 
            msg = '**Warning:** The following user(s) cannot be requested as they are not competitors: `' + '`, `'.join(_users_unauthorized) + '`. ' + res_msg
            await ctx.send(msg, **msg_settings)

        if _users_not_found:
            # send message saying the users weren't found. 
            msg = '**Warning:** Unable to find user(s): `' + '`, `'.join(_hack_san(x) for x in _users_not_found) + '`. ' + res_msg
            await ctx.send(msg, **msg_settings)

        # XXX: search for previous commands, and drop the old check mark if exists.
        await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


async def _set_team_locked(ctx, locked: bool) -> bool:
    author = _get_db_user_from_ctx(ctx)
    logging.debug('_set_team_locked: author=%r, locked=%r' % (author, locked))
    if author.get('lock_team', False) == locked:
        await ctx.send('**Error:** Your team is already locked to the users: ' + ' '.join(list({str(ctx.author)} | set(_get_db_user_from_ctx(ctx).get('team_requests', [])))) + '. You may unlock your team by running the command `!unlock-team`.', **msg_settings)
        return False

    tags = set(author.get('team_requests', [])) | {str(ctx.author)}
    logging.debug('_set_team_locked: all tags: %r' % tags)

    problems = dict()
    for tag in tags:
        user = _get_db_user_from_user(tag)
        # make sure users requested each other
        if set(user.get('team_requests', [])) | {tag} != tags:
            problems[tag] = {
                'requested': list(set(user.get('team_requests', []))),
                'should_request': list(tags - {tag})
            }

    logging.debug('_set_team_locked: problems: %r' % problems)
    if problems:
        if locked:
            teammates_msg = list()
            # we're trying to lock the team

            for tag, data in problems.items():
                member_obj = await resolve_user(ctx, tag, use_cache=True)
                if not member_obj:
                    # don't exit, just warn
                    logging.warning('_set_team_locked: Unable to find member object for member %r %r!' % (tag, data))
                    continue
                
                teammates_msg.append('  *  ' + member_obj.mention + ': `!request ' + ' '.join(data['should_request']) + '` (currently requested: ' + (' '.join(data['requested']) or 'none') + ')')
            
            await ctx.send(f'Hey {ctx.author.mention}, it looks like some of your teammates have not confirmed that they want to be a part of your team. Please have the following users execute their respective `!request` commands to confirm membership in the team, then run the `!lock-team` command again:\n' + '\n'.join(teammates_msg), **msg_settings)
            return False
        else:
            # we're trying to reset the lock
            await ctx.send(ctx, 'It looks like the user(s) you requested, %s, is/are not a part of your team.' % (' '.join(str(x) for x in problems.keys())), **msg_settings)
            return False


    for tag in tags:
        user = _get_db_user_from_user(tag)
        user['lock_team'] = locked

    db.write()
    return True


@client.command(name='lock-team', pass_context=True)
async def lockteam(ctx: discord.ext.commands.context.Context, *args) -> None:
    if ctx.channel.id == config['discord']['team-requests']['channel-id']:
        num_teammates_requested = len(_get_db_user_from_ctx(ctx).get('team_requests', []))
        if num_teammates_requested >= 4:
            await ctx.send(ctx, '**Error:** You requested %d teammates, but the maximum team size is 4. Use `!request [usernames...]` to request up to 3 other people to be on your team.' % num_teammates_requested, **msg_settings)
            return 

        if await _set_team_locked(ctx, True):
            await ctx.send('Locked your team to the users: ' + ' '.join(list({str(ctx.author)} | set(_get_db_user_from_ctx(ctx).get('team_requests', [])))) + '. You and your teammates may no longer request additional teammates. If you need to modify your teammate selection, run `!unlock-team` or contact an admin for help.', **msg_settings)
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')



@client.command(name='unlock-team', pass_context=True)
async def unlockteam(ctx: discord.ext.commands.context.Context, *args) -> None:
    if ctx.channel.id == config['discord']['team-requests']['channel-id']:
        if not _get_db_user_from_ctx(ctx).get('lock_team', False):
            await ctx.send('**Error:** You aren\'t in a team that was locked. Please contact an admin if you believe you are receiving this message in error.', **msg_settings)
            return
        
        if await _set_team_locked(ctx, False):
            await ctx.send('Unlocked your team. You and your teammates may now request other users.', **msg_settings)
            await ctx.message.add_reaction('\N{WHITE HEAVY CHECK MARK}')


MAKETEAMS_LOCK = False
@client.command(pass_context=True)
async def maketeams(ctx: discord.ext.commands.context.Context, *args) -> None:
    global MAKETEAMS_LOCK

    if MAKETEAMS_LOCK:
        await ctx.send('Team generation already in progress, ignoring additional request...', **msg_settings)
        return

    MAKETEAMS_LOCK = True

    if ctx.channel.id == config['discord']['maketeams']['channel-id']:
        channel = ctx.guild.get_channel(int(config['discord']['specializations']['channel-id']))
        msg = await channel.fetch_message(int(config['discord']['specializations']['message-id']))

        # reset specialities
        for username in db.db['users']:
            if 'specialities' in db.db['users'][username]:
                del db.db['users'][username]['specialities']

        #  get_competitors() and make sure they all exist in the db
        for user in await get_competitors(ctx):
            username = str(user)
            if username not in db.db['users']:
                db.db['users'][username] = dict()

        # parse reactions => specialities
        logging.info('maketeams: parsing reactions...')
        for reaction in msg.reactions:
            emoji_name = _emoji_to_name(reaction.emoji)

            # if the emoji is meaningless, skip it
            if not (speciality := config['discord']['specializations']['emojis'].get(emoji_name)):
                continue

            async for user in reaction.users(limit=None, after=None):
                user_dict = _get_db_user_from_user(user)
                if 'specialities' not in user_dict:
                    user_dict['specialities'] = list()

                user_dict['specialities'].append(speciality)
                db.write()

        await ctx.send('Generating optimized teams, please wait (this may take a few minutes)...', **msg_settings)

        teams = list()
        _teams_locked = dict()

        user_requests = list()
        for username, details in db.db['users'].items():
            if details.get('lock_team', False):
                if username not in _teams_locked:
                    team_locked = [
                        {'username': x}
                        for x in
                        list({username} | set(details.get('team_requests', list())))
                    ]
                    teams.append(team_locked)
                    for member in details.get('team_requests', list()):
                        _teams_locked[member] = team_locked

            else:
                user_request = {
                    'username': username,
                    'noob': 'noob' in details.get('specialities', list()),
                    'specialities': list(set(details.get('specialities', list())) - {'noob'}),
                    'team_requests': details.get('team_requests', list())
                }
                user_requests.append(user_request)

        logging.info('locked teams: %r' % teams)
        logging.info('user_requests: %r' % user_requests)
        start_time = time.time()
        teams.extend(teamutil.get_optimized_teams(user_requests))
        logging.info('generated teams: %r' % teams)

        await ctx.send(f'Formed {len(teams)} teams of {teamutil.TEAM_SIZE} people in %.2f seconds.' % (time.time() - start_time), **msg_settings)

        team_no = 1
        category = await ctx.guild.create_category('Teams')
        for team in teams:
            team_name = 'team-%d' % team_no
            permissions = {
                ctx.guild.default_role: discord.PermissionOverwrite(read_messages=False),
                ctx.guild.me: discord.PermissionOverwrite(read_messages=True),
                discord.utils.get(ctx.guild.roles, name='Organizers'): discord.PermissionOverwrite(read_messages=True)
            }

            for member in team:
                permissions[await resolve_user(ctx, member['username'], use_cache=True)] = discord.PermissionOverwrite(read_messages=True)

            channel = await ctx.guild.create_text_channel(team_name, category=category, topic=f'Discuss your HackOR project with your team ({team_name}) here.', overwrites=permissions)

            teammates_msg = ''
            for member in team:
                member_obj = await resolve_user(ctx, member['username'], use_cache=False)
                if not member_obj:
                    # don't exit, just warn
                    logging.warning('Unable to find member object for member %r!' % member)
                    continue
                
                teammates_msg += f'  *  ' + (member_obj.mention if not TESTING_MODE else member['username'])
                if member.get('specialities'):
                    teammates_msg += ' (' + ', '.join(member['specialities']) + ')'
                teammates_msg += '\n'

            message = await channel.send('''Hello! I created this channel for you and your new team. You may discuss your project or other group details here.

Let me introduce you to your teammates:
''' + teammates_msg + '''
Start off by figuring out what you are all interested in, and figure out what project you want to make. Note that you don't have to use this channel to communicate if you prefer to communicate via other means.''', **msg_settings)
            await message.pin()

            team_no += 1


    else:
        await ctx.send('Wrong channel.', **msg_settings) # we use message send permission in channels for access control

    MAKETEAMS_LOCK = False


@client.command(pass_context=True)
async def ping(ctx: discord.ext.commands.context.Context) -> None:
    await ctx.send('Pong! I am alive.', **msg_settings)

    #channel = ctx.guild.get_channel(int(config['discord']['specializations']['channel-id']))
    #msg = await channel.fetch_message(int(config['discord']['specializations']['message-id']))
    #
    #for name in config['discord']['specializations']['emojis']:
    #    await msg.add_reaction(name) # BUG: have to convert name => emoji name => emoji unicode somehow


##########


if __name__ == '__main__':
    with open('config.yml', 'r') as f:
        config = yaml.safe_load(f.read())
        token = config.get('discord', {}).get('token')
        assert token, 'Config is missing discord.token'

    db.read()

    client.run(token)
