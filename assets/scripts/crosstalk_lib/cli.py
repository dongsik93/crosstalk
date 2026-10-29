"""Protocol 3 CLI with compatible ordinary mailbox and opt-in discussion commands."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from . import ENGINE_VERSION, PROTOCOL_VERSION, RUNTIME_VERSION, SCHEMA_VERSION, db, doctor, migrations, sessions
from .protocol import Error, now, require


class Parser(argparse.ArgumentParser):
    def error(self,message):
        raise Error('INVALID_ARGUMENT',message)


def parser():
    result=Parser(description='Crosstalk mailbox protocol 3 and discussion engine 1')
    commands=result.add_subparsers(dest='command',required=True,parser_class=Parser)
    capabilities=commands.add_parser('capabilities')
    capabilities.add_argument('--json',action='store_true')
    from .engine import service
    service.add_parser(commands)
    from . import intake
    intake.add_parser(commands)
    migrations.add_parser(commands)
    sessions.add_parser(commands)
    doctor.add_parser(commands)
    for name in ('send','reply'):
        sub=commands.add_parser(name)
        sub.add_argument('peer' if name=='send' else 'id')
        sub.add_argument('text',nargs='?')
        sub.add_argument('--stdin',action='store_true')
        sub.add_argument('--summary',default='')
        sub.add_argument('--lease-token')
        if name=='send':
            sub.add_argument('--id')
            sub.add_argument('--thread')
            sub.add_argument('--after-reply')
            sub.add_argument('--peer-session',help='Explicit logical recipient session ID')
            sub.add_argument('--mode',choices=('analyze','ask'),default='analyze')
        else:
            sub.add_argument('--verdict',choices=('agree','disagree','respect_disagree','none'),default='none')
            sub.add_argument('--reason',default='')
            sub.add_argument('--confidence',choices=('high','medium','low','unknown'),default='unknown')
    receive=commands.add_parser('receive')
    receive.add_argument('id',nargs='?')
    receive.add_argument('--replay',action='store_true',help='Deprecated: use explicit recover instead')
    ack=commands.add_parser('ack')
    ack.add_argument('id')
    ack.add_argument('--lease-token')
    ack.add_argument('--outcome',choices=('concluded','diverged','unresolved','observed'),required=True)
    ack.add_argument('--result-stdin',action='store_true',required=True)
    renew=commands.add_parser('renew')
    renew.add_argument('id')
    renew.add_argument('--lease-token')
    recover=commands.add_parser('recover')
    recover.add_argument('id')
    recover.add_argument('--reclaim',action='store_true')
    recover.add_argument('--expected-claim-version',type=int)
    recover.add_argument('--confirm-external-effects',action='store_true')
    cancel=commands.add_parser('cancel')
    cancel.add_argument('id')
    cancel.add_argument('--reason',required=True)
    commands.add_parser('retry').add_argument('id')
    for name in ('history','status'):
        sub=commands.add_parser(name)
        sub.add_argument('id',**({'nargs':'?'} if name=='status' else {}))
        sub.add_argument('--limit',type=int,default=50)
        sub.add_argument('--offset',type=int,default=0)
    # Independent command families share this entry point, not mailbox transactions.
    from . import reviews, installer
    reviews.add_parser(commands)
    installer.add_parser(commands)
    return result


def capabilities():
    script_root=Path(__file__).resolve().parents[1]
    instructions=script_root.parent/'codex-skills/crosstalk/mailbox.md'
    health='source_checkout'
    try:
        from . import installer
        installation=installer.inspect(db.root())
        health=installation
    except (ImportError,AttributeError):
        health='unmanaged'
    version=None
    if (db.root()/'mailbox.sqlite3').exists():
        try:
            conn=sqlite3.connect((db.root()/'mailbox.sqlite3').as_uri()+'?mode=ro',uri=True)
            try: version=db.schema_version(conn)
            finally: conn.close()
        except (sqlite3.Error,Error): version='unsupported'
    return {'runtime_version':RUNTIME_VERSION,'protocol_version':PROTOCOL_VERSION,'schema_version':version,
            'engine_version':ENGINE_VERSION,'engine_available':True,'engine_default':False,
            'independent_review_available':True,
            'independent_instructions':str(script_root.parent/'codex-skills/crosstalk/independent.md'),
            'discussion_instructions':str(script_root.parent/'codex-skills/crosstalk/discussion.md'),
            'supported_schema_version':SCHEMA_VERSION,'backend':'ghostty','installation_health':health,
            'mailbox_instructions':str(instructions),'supported_commands':['input','run','capabilities','migrate','session','send','receive','reply','ack','renew','retry','recover','cancel','status','history','doctor','review','install','uninstall']}


def maintenance():
    require(not (db.root()/'maintenance.json').exists(), 'INSTALLATION_INCOMPLETE','Installation is in maintenance; finish or repair installation first')
    from . import installer
    try:
        health=installer.inspect(db.root())
    except (ValueError, OSError, KeyError, TypeError):
        raise Error('INSTALLATION_INCOMPLETE','Installation cannot be verified; run doctor --offline') from None
    require(health['status'] in ('healthy','unmanaged'), 'INSTALLATION_INCOMPLETE',
            'Installation files or runtime do not match; run doctor --offline and repair installation')


def dispatch(args):
    if args.command=='capabilities': return capabilities()
    if args.command=='migrate': return migrations.run(args)
    if args.command=='doctor': return doctor.run(args)
    if args.command in ('install','uninstall'):
        from . import installer
        return installer.run(args)
    if args.command=='input':
        from . import intake
        return intake.run(args)
    readonly=(args.command=='run' and args.run_command in ('next','status','report','export')) or args.command in ('status','history') or (args.command=='recover' and not args.reclaim) or (args.command=='session' and args.session_command=='status')
    if not readonly: maintenance()
    if args.command=='run':
        from .engine import service
        return service.run(args)
    if args.command=='review':
        from . import reviews
        return reviews.run(args)
    if args.command=='session': return sessions.run(args)
    from . import mailbox
    if hasattr(args,'limit'): require(args.limit>0 and args.offset>=0, 'INVALID_ARGUMENT','Use a positive limit and nonnegative offset')
    body=None
    if args.command in ('send','reply'):
        require(not (args.stdin and args.text is not None),'INVALID_ARGUMENT','Choose text or --stdin')
        body=sys.stdin.read() if args.stdin else args.text
        require(body is not None and body.strip(),'INVALID_ARGUMENT','A nonempty message is required')
    conn=db.connect(readonly=readonly)
    try:
        actor=sessions.actor(conn)
        if args.command in ('status','history'): return mailbox.query(conn,actor,args)
        if args.command in ('send','reply'): return getattr(mailbox,args.command)(conn,actor,args,body)
        if args.command=='ack':
            result=sys.stdin.read()
            require(result.strip(),'INVALID_ARGUMENT','A completion result is required on stdin')
            return mailbox.ack(conn,actor,args,result)
        if args.command=='retry':
            from . import delivery
            row=mailbox.message(conn,args.id,actor)
            require(row['sender_session_id']==actor['session_id'],'STATE_CONFLICT','Only the sender may retry notifications')
            result=mailbox.output(conn,args.id,actor)
            result.update(delivery.notify(conn,row,retry=True))
            return result
        return getattr(mailbox,args.command)(conn,actor,args)
    finally: conn.close()


def main(argv=None):
    os.umask(0o077)
    try:
        result=dispatch(parser().parse_args(argv))
        print(json.dumps(result,ensure_ascii=False))
        if isinstance(result,dict) and result.get('error'):
            return Error(result['error']['code'],result['error']['message']).exit_code
        return 4 if isinstance(result,dict) and result.get('delivery_state') in ('failed','unknown') else 0
    except Error as exc:
        print(json.dumps(exc.result(),ensure_ascii=False))
        print(str(exc),file=sys.stderr)
        return exc.exit_code
    except (OSError,sqlite3.Error,ValueError,SyntaxError,subprocess.SubprocessError) as exc:
        code=getattr(exc,'code','DB_BUSY' if isinstance(exc,sqlite3.OperationalError) and 'locked' in str(exc) else 'OPERATION_FAILED')
        error=Error(code,str(exc))
        print(json.dumps(error.result(),ensure_ascii=False))
        print(str(exc),file=sys.stderr)
        return error.exit_code
