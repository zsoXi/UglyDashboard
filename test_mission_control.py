"""Offline regression suite; all projects, API responses and sessions are fixtures."""
import base64
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler
from urllib.error import HTTPError
from urllib.parse import urlencode, urlparse, parse_qs

FILE = Path(__file__).parent / 'opencode_dashboard.py'
if not FILE.exists():
    FILE = Path('/mnt/data/opencode_dashboard.py')
spec = importlib.util.spec_from_file_location('mc_test_app', FILE)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def fixture_db(root):
    db = Path(root) / 'opencode.db'; project = str(Path(root) / 'Campus testowy'); Path(project).mkdir(exist_ok=True)
    con = sqlite3.connect(db)
    con.executescript('''CREATE TABLE project(id TEXT PRIMARY KEY,name TEXT,worktree TEXT);
    CREATE TABLE session(id TEXT PRIMARY KEY,project_id TEXT,parent_id TEXT,directory TEXT,title TEXT,time_created INTEGER,time_updated INTEGER);
    CREATE TABLE message(id TEXT PRIMARY KEY,session_id TEXT,time_created INTEGER,data TEXT);
    CREATE TABLE part(id TEXT PRIMARY KEY,session_id TEXT,message_id TEXT,time_created INTEGER,data TEXT);''')
    con.execute('INSERT INTO project VALUES(?,?,?)', ('p', 'Campus testowy', project))
    now = m.now_ms()
    for i,(sid,parent,title) in enumerate([('s-root',None,'Przebudowa panelu'),('s-child','s-root','Worker interfejsu'),('s-fork','s-root','Fork do eksperymentu')]):
        con.execute('INSERT INTO session VALUES(?,?,?,?,?,?,?)', (sid,'p',parent,project,title,now-120000-i*1000,now-1000-i*100))
        user={'role':'user','time':{'created':now-60000}}
        info={'role':'assistant','agent':'tl-1' if i==0 else 'worker-ui','modelID':'fixture-flash' if i!=1 else 'fixture-pro','providerID':'fixture','time':{'created':now-50000,'completed':now-2000}, 'tokens':{'input':200,'output':30,'reasoning':10,'cache':{'read':60,'write':0},'total':300}, 'cost':0.01}
        con.execute('INSERT INTO message VALUES(?,?,?,?)',(sid+'-u',sid,now-60000,json.dumps(user)))
        con.execute('INSERT INTO message VALUES(?,?,?,?)',(sid+'-a',sid,now-50000,json.dumps(info)))
        con.execute('INSERT INTO part VALUES(?,?,?,?,?)',(sid+'-text',sid,sid+'-u',now-60000,json.dumps({'type':'text','text':'Popraw panel <img src=x onerror="window.__xss=1">'})))
        con.execute('INSERT INTO part VALUES(?,?,?,?,?)',(sid+'-usage',sid,sid+'-a',now-10000,json.dumps({'type':'step-finish','tokens':info['tokens'],'cost':0.01})))
    task={'type':'tool','tool':'task','callID':'call-task','state':{'status':'completed','input':{'description':'UI worker'},'metadata':{'sessionId':'s-child'},'output':'Done'}}
    con.execute('INSERT INTO part VALUES(?,?,?,?,?)',('p-task','s-root','s-root-a',now-15000,json.dumps(task)))
    edit={'type':'tool','tool':'edit','callID':'edit-1','state':{'status':'completed','input':{'filePath':str(Path(project)/'app.tsx')},'output':'Updated'}}
    con.execute('INSERT INTO part VALUES(?,?,?,?,?)',('p-edit','s-child','s-child-a',now-12000,json.dumps(edit)))
    con.commit();con.close()
    return str(db), project


def fixture_codex(root):
    home=Path(root)/'.codex';logs=home/'sessions'/'2026'/'09'/'16';logs.mkdir(parents=True)
    ts=m.datetime.now(m.timezone.utc)
    def row(kind,payload,i):
        return {'timestamp':(ts+m.timedelta(seconds=i-100)).isoformat(),'type':kind,'payload':payload}
    records=[row('session_meta',{'id':'cx-1','cwd':str(Path(root)/'Codex project'),'originator':'codex_fixture'},0),
             row('turn_context',{'model':'fixture-codex'},1),
             row('event_msg',{'type':'task_started','turn_id':'turn-1'},2),
             row('response_item',{'type':'message','role':'user','content':[{'type':'input_text','text':'Sprawdź testy'}]},3),
             row('response_item',{'type':'function_call','name':'exec_command','call_id':'c1','arguments':json.dumps({'cmd':'python -m unittest'})},4),
             row('response_item',{'type':'function_call_output','call_id':'c1','output':'Process exited with code 0\nOK'},5)]
    usage={'input_tokens':1000,'cached_input_tokens':700,'output_tokens':200,'reasoning_output_tokens':50,'total_tokens':1200}
    for i in (6,7):
        records.append(row('event_msg',{'type':'token_count','info':{'total_token_usage':usage,'last_token_usage':usage,'model_context_window':100000}},i))
    records.append(row('event_msg',{'type':'task_complete','turn_id':'turn-1'},8))
    path=logs/'rollout-test.jsonl';path.write_text(''.join(json.dumps(x)+'\n' for x in records),'utf-8')
    return str(home),path


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name)
    def tearDown(self):
        self.tmp.cleanup()


class ParsingTests(Base):
    def test_schema_without_agent_columns(self):
        db,_=fixture_db(self.root);sessions,_,coverage=m.read_opencode(db)
        self.assertEqual(len(sessions),3);self.assertFalse(coverage['truncated'])
        self.assertEqual(next(s for s in sessions if s['native_id']=='s-root')['agent'],'tl-1')
    def test_parts_not_double_counted_with_messages(self):
        db,_=fixture_db(self.root);sessions,_,_=m.read_opencode(db)
        self.assertEqual(sum(s['usage']['total'] for s in sessions),900)
    def test_fork_not_classified_subagent(self):
        db,_=fixture_db(self.root);sessions,_,_=m.read_opencode(db);by={s['native_id']:s for s in sessions}
        self.assertEqual(by['s-child']['relationship'],'delegated')
        self.assertEqual(by['s-fork']['relationship'],'parent_unknown')
    def test_database_is_readonly(self):
        db,_=fixture_db(self.root)
        with m.readonly_db(db) as con:
            with self.assertRaises(sqlite3.OperationalError):con.execute('DELETE FROM session')
    def test_schema_error_clear(self):
        db=self.root/'empty.db';sqlite3.connect(db).close()
        with self.assertRaisesRegex(ValueError,'Unsupported OpenCode schema'):m.read_opencode(db)
    def test_missing_db_not_created(self):
        db=self.root/'missing.db'
        with self.assertRaises(FileNotFoundError):
            with m.readonly_db(db):pass
        self.assertFalse(db.exists())
    def test_coverage_limit(self):
        db,_=fixture_db(self.root);rows,_,cov=m.read_opencode(db,1)
        self.assertEqual(len(rows),1);self.assertTrue(cov['truncated']);self.assertEqual(cov['total_sessions'],3)
    def test_codex_cumulative_and_reasoning(self):
        home,p=fixture_codex(self.root);reader=m.JsonlReader();s=m.make_session('codex','rollout-test')
        m.codex_apply(s,reader.read(p));self.assertEqual(s['usage']['total'],1200)
        self.assertEqual(s['usage']['input'],300);self.assertEqual(s['usage']['output'],150)
        self.assertEqual(s['usage']['reasoning'],50);self.assertEqual(s['usage']['cache_read'],700)
    def test_codex_complete_explicit(self):
        _,p=fixture_codex(self.root);s=m.make_session('codex','rollout-test');m.codex_apply(s,m.JsonlReader().read(p))
        self.assertEqual(s['state'],'done');self.assertEqual(s['confidence'],'recorded')
    def test_codex_agent_calls_not_test_quality(self):
        _,p=fixture_codex(self.root);s=m.make_session('codex','x');m.codex_apply(s,m.JsonlReader().read(p))
        self.assertNotIn('tests_passed',s);self.assertEqual(s['tools'][0]['exit_code'],0)
    def test_codex_delegation(self):
        s=m.make_session('codex','x');m.codex_apply(s,[{'type':'session_meta','payload':{'id':'c','source':{'subagent':{'thread_spawn':{'parent_thread_id':'p'}}}}}])
        self.assertEqual(s['parent_id'],'codex:p');self.assertEqual(s['relationship'],'delegated')
    def test_codex_fork_separate(self):
        s=m.make_session('codex','x');m.codex_apply(s,[{'type':'session_meta','payload':{'id':'c','forked_from_id':'p'}}])
        self.assertEqual(s['relationship'],'fork')
    def test_partial_jsonl_and_utf8(self):
        p=self.root/'log';text=json.dumps({'name':'żółć'},ensure_ascii=False).encode();r=m.JsonlReader();p.write_bytes(text[:12]);self.assertEqual(r.read(p),[])
        with p.open('ab') as f:f.write(text[12:]+b'\n')
        self.assertEqual(r.read(p),[{'name':'żółć'}]);self.assertEqual(r.read(p),[])
    def test_long_line_skip_recovers(self):
        p=self.root/'log';p.write_bytes(b'x'*(m.MAX_LINE+1024)+b'\n{"ok":true}\n');r=m.JsonlReader()
        self.assertEqual(r.read(p),[{'ok':True}]);self.assertEqual(r.skipped,1)
    def test_truncate_rewrite_grows(self):
        p=self.root/'log';p.write_text('{"old":1}\n');r=m.JsonlReader();r.read(p)
        p.write_text('{"new_value":12345}\n{"new_value":56789}\n')
        out=r.read(p);self.assertTrue(r.reset);self.assertEqual(len(out),2);self.assertEqual(out[0]['new_value'],12345)
    def test_jsonl_nonfinite_rejected(self):
        p=self.root/'nonfinite';p.write_text('{"time":NaN}\n{"ok":1}\n');r=m.JsonlReader()
        self.assertEqual(r.read(p),[{'ok':1}]);self.assertEqual(r.skipped,1)
        self.assertEqual(m.stamp(float('nan')),0)
    def test_rotation(self):
        p=self.root/'log';p.write_text('{"old":1}\n');r=m.JsonlReader();r.read(p);p.rename(self.root/'previous');p.write_text('{"new":2}\n')
        self.assertEqual(r.read(p),[{'new':2}]);self.assertTrue(r.reset)
    def test_invalid_json_count(self):
        p=self.root/'log';p.write_text('not json\n{"x":1}\n');r=m.JsonlReader();self.assertEqual(r.read(p),[{'x':1}]);self.assertEqual(r.skipped,1)
    def test_tail_budget(self):
        p=self.root/'log';p.write_bytes(b'{"x":1}\n'*1000);r=m.JsonlReader();a=r.read(p,budget=100)
        self.assertLess(r.offset,p.stat().st_size);self.assertGreater(len(a),0)
    def test_num_nonfinite(self):
        for x in (float('nan'),float('inf'),-3,'no',None):self.assertEqual(m.number(x),0)
    def test_path_boundaries(self):
        self.assertTrue(m.is_within(r'D:\PROJECT\src\a',r'd:\project'));self.assertFalse(m.is_within('/app2/file','/app'))
    def test_secret_masking(self):
        text=m.redact('api_key=verysecretvalue Bearer ABCDEF sk-12345678901234567890')
        self.assertNotIn('verysecretvalue',text);self.assertNotIn('ABCDEF',text);self.assertNotIn('sk-123',text)


class ConfigScanTests(Base):
    def test_defaults_no_hardcoded_testy(self):
        self.assertNotIn('TESTY',json.dumps(m.default_config()))
    def test_remote_opencode_denied(self):
        for url in ['http://192.168.1.1:4096','https://example.com','http://user:pass@127.0.0.1:4096','http://127.0.0.1:4096/path']:
            with self.assertRaises(ValueError):m.validate_config({'opencode_urls':[url]})
    def test_public_origin_https(self):
        with self.assertRaises(ValueError):m.validate_config({'public_origin':'http://example.com'})
    def test_config_unknown_key_rejected(self):
        with self.assertRaises(ValueError):m.validate_config({'shell_command':'rm'})
    def test_limits_checked(self):
        for val in (-1,float('inf'),True,10000):
            with self.assertRaises(ValueError):m.validate_config({'poll_seconds':val})
    def test_pricing_validation(self):
        with self.assertRaises(ValueError):m.validate_config({'pricing':{'x':{'input':-1}}})
        with self.assertRaises(ValueError):m.validate_config({'pricing':{'x':{'foo':1}}})
    def test_scan_markers(self):
        project=self.root/'repo';project.mkdir();(project/'.git').mkdir();(project/'.opencode').mkdir();db=project/'opencode.db';db.touch()
        result=m.scan_paths([str(self.root)],depth=2)
        self.assertEqual({i['kind'] for i in result['items']},{'project','database'})
    def test_scan_no_symlink_traversal(self):
        outside=self.root/'outside';outside.mkdir();(outside/'.git').mkdir();scan=self.root/'scan';scan.mkdir()
        try:(scan/'linked').symlink_to(outside,target_is_directory=True)
        except OSError:self.skipTest('Creating symlinks is unavailable in this environment.')
        self.assertEqual(m.scan_paths([str(scan)])['items'],[])
    def test_scan_reports_limits(self):
        for i in range(10):(self.root/str(i)).mkdir()
        self.assertTrue(m.scan_paths([str(self.root)],max_dirs=2)['truncated'])
    def test_scan_missing_folder_reported(self):
        self.assertTrue(m.scan_paths([str(self.root/'missing')])['errors'])


class EngineTests(Base):
    def make_engine(self,extras=None):
        db,project=fixture_db(self.root);home,log=fixture_codex(self.root)
        cfg={'db_paths':[db],'codex_homes':[home],'router_events':[],'opencode_urls':[],'projects':[project],'git_enabled':False}
        cfg.update(extras or {});e=m.Engine(self.root/'state',cfg);self.addCleanup(e.close);e.poll();return e
    def test_combined_counts(self):
        e=self.make_engine();v=e.view();self.assertEqual(len(v['sessions']),4);self.assertEqual(v['tokens'],2100);self.assertEqual(v['verified_active'],0)
    def test_repeat_poll_no_double_count(self):
        e=self.make_engine();n=e.view()['tokens'];e.poll();self.assertEqual(e.view()['tokens'],n)
    def test_source_files_unchanged(self):
        e=self.make_engine();paths=e.cfg['db_paths']+[str(next(Path(e.cfg['codex_homes'][0]).rglob('*.jsonl')))];before=[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths]
        e.poll();after=[hashlib.sha256(Path(p).read_bytes()).hexdigest() for p in paths];self.assertEqual(before,after)
    def test_report_disabled(self):
        e=self.make_engine()
        with self.assertRaises(PermissionError):e.add_report({'event_id':'x','session_id':'s','source':'chatgpt'})
    def test_report_idempotent_and_persists_no_timestamp(self):
        e=self.make_engine({'enable_reporting':True});data={'event_id':'x','session_id':'opencode:s-root','source':'chatgpt','task':'Actual task'}
        self.assertFalse(e.add_report(data)['duplicate']);self.assertTrue(e.add_report(data)['duplicate']);e.poll()
        self.assertEqual(e.detail('opencode:s-root')['origin'],'chatgpt');self.assertEqual(len(e.store.reports()),1);self.assertEqual(e.view()['tokens'],2100)
    def test_report_duplicate_conflict(self):
        e=self.make_engine({'enable_reporting':True});d={'event_id':'x','session_id':'opencode:s-root','source':'chatgpt'};e.add_report(d)
        with self.assertRaises(ValueError):e.add_report({**d,'task':'changed'})
    def test_report_not_override_native_status(self):
        e=self.make_engine({'enable_reporting':True});e.add_report({'event_id':'x','session_id':'codex:cx-1','source':'chatgpt','state':'running'});e.poll()
        self.assertEqual(e.detail('codex:cx-1')['state'],'done')
    def test_report_new_session_not_live_verified(self):
        e=self.make_engine({'enable_reporting':True});e.add_report({'event_id':'x','session_id':'reported:chatgpt:thread','source':'chatgpt','state':'running'});e.poll()
        s=e.detail('reported:chatgpt:thread');self.assertEqual(s['confidence'],'reported');self.assertEqual(s['state'],'running');self.assertGreater(s['updated'],0)
    def test_unknown_quality_not_zero(self):
        e=self.make_engine();a=e.analytics();self.assertTrue(all(x['test_pass_rate'] is None for x in a['models']))
    def test_owner_assessment_metrics(self):
        e=self.make_engine();e.assess('opencode:s-child',{'task_group':'same-task','tests_passed':False,'review_fixes':3,'duration_seconds':120})
        a=e.analytics(task_group='same-task');self.assertEqual(a['sessions'],1);self.assertEqual(a['models'][0]['test_pass_rate'],0);self.assertEqual(a['models'][0]['test_samples'],1)
    def test_invalid_assessment(self):
        e=self.make_engine()
        with self.assertRaises(ValueError):e.assess('opencode:s-child',{'review_fixes':-3})
    def test_token_pricing_unknown(self):
        e=self.make_engine();self.assertTrue(all(x['estimated_cost'] is None for x in e.analytics()['models']))
    def test_expected_model_alert(self):
        e=self.make_engine({'expected_models':{'worker-ui':'fixture-flash'}})
        self.assertTrue(any(a['kind']=='model_mismatch' for a in e.view()['alerts']))
    def test_no_implicit_abort(self):
        e=self.make_engine()
        with self.assertRaises(PermissionError):e.abort('opencode:s-root','s-root')
    def test_live_expiration(self):
        e=self.make_engine()
        with e.lock:
            s=e.snapshot['sessions'][0];s.update(state='running',confidence='verified',observed=m.now_ms()-120000)
        self.assertEqual(e.view()['sessions'][0]['state'],'stale');self.assertEqual(e.view()['verified_active'],0)
    def test_detail_verified_state_ages(self):
        e=self.make_engine()
        with e.lock:e.sessions['opencode:s-root'].update(state='running',confidence='verified',observed=m.now_ms()-120000)
        d=e.detail('opencode:s-root');self.assertEqual(d['state'],'stale');self.assertEqual(d['confidence'],'unknown')
    def test_prompts_can_be_suppressed(self):
        e=self.make_engine({'show_prompts':False});self.assertEqual(e.detail('opencode:s-root')['prompt'],'');self.assertFalse(any(s['task_preview'] for s in e.view()['sessions']))
    def test_model_filter_source(self):
        e=self.make_engine();self.assertEqual(e.analytics(source='codex')['tokens'],1200)
    def test_router_excluded_from_combined(self):
        e=self.make_engine();p=self.root/'router.jsonl';p.write_text(json.dumps({'at':m.datetime.now(m.timezone.utc).isoformat(),'model':'fixture','status':200,'inputTokens':100,'outputTokens':20})+'\n');cfg=e.config();cfg['router_events']=[str(p)];e.save_config(cfg);e.poll()
        self.assertEqual(e.view()['tokens'],2100);self.assertEqual(e.view()['router'][0]['tokens'],120)
    def test_source_health_identity(self):
        e=self.make_engine();self.assertEqual(e.view()['version'],m.VERSION)
    def test_readonly_paths_sanitized_in_mcp(self):
        e=self.make_engine();s=e.detail('opencode:s-root');self.assertNotIn('_db',s)


class StoreTests(Base):
    def test_event_dedup_and_cursor(self):
        s=m.Store(self.root);self.addCleanup(s.close)
        items=[{'id':str(i),'ts':m.now_ms(),'session_id':'s','kind':'x','text':str(i)} for i in range(3)]
        s.events(items);s.events(items);a=s.timeline(2);b=s.timeline(2,a['next_before']);self.assertEqual(len(a['events'])+len(b['events']),3)
    def test_secret_stable(self):
        s=m.Store(self.root);self.addCleanup(s.close);self.assertEqual(s.secret('key'),s.secret('key'));self.assertGreater(len(s.secret('key')),32)
    @unittest.skipUnless(os.name == 'posix', 'POSIX file-mode assertion; Windows uses account ACLs.')
    def test_restricted_secret_permissions(self):
        s=m.Store(self.root);self.addCleanup(s.close);s.secret('key');self.assertEqual((self.root/'key').stat().st_mode & 0o777,0o600)


class ProtocolTests(Base):
    def setUp(self):
        super().setUp();self.e=m.Engine(self.root/'state',{'db_paths':[],'codex_homes':[],'router_events':[],'opencode_urls':[],'git_enabled':False});self.e.poll()
        self.srv=m.Server(('127.0.0.1',0),self.e);self.port=self.srv.server_address[1];self.url=f'http://127.0.0.1:{self.port}'
        self.t=threading.Thread(target=self.srv.serve_forever,daemon=True);self.t.start();self.http=build_opener(ProxyHandler({}),m.NoRedirect())
    def tearDown(self):
        self.srv.shutdown();self.srv.server_close();self.t.join();self.e.close();super().tearDown()
    def request(self,path,body=None,token='owner',headers=None,form=False):
        h=dict(headers or {})
        if token=='owner':h['Authorization']='Bearer '+self.e.control_token
        elif token=='mcp':h['Authorization']='Bearer '+self.e.mcp_token
        elif token:h['Authorization']='Bearer '+token
        data=None
        if body is not None:
            if form:h['Content-Type']='application/x-www-form-urlencoded';data=urlencode(body).encode()
            else:h['Content-Type']='application/json';data=json.dumps(body).encode()
        req=Request(self.url+path,data=data,headers=h)
        try:
            r=self.http.open(req,timeout=5);status=r.status;headers=dict(r.headers);raw=r.read();r.close()
        except HTTPError as e:status=e.code;headers=dict(e.headers);raw=e.read()
        try:out=json.loads(raw)
        except ValueError:out=raw.decode()
        return status,out,headers
    def rpc(self,method,params=None,token='mcp',rid=1):return self.request('/mcp',{'jsonrpc':'2.0','id':rid,'method':method,'params':params or {}},token)
    def test_unauth_api_denied(self):self.assertEqual(self.request('/api/overview',token=None)[0],401)
    def test_static_page_no_secrets(self):
        status,body,_=self.request('/',token=None);self.assertEqual(status,200);self.assertNotIn(self.e.control_token,body)
    def test_mcp_token_cannot_configure(self):self.assertEqual(self.request('/api/config',token='mcp')[0],403)
    def test_host_rebinding_denied(self):self.assertEqual(self.request('/api/overview',headers={'Host':'evil.example'})[0],403)
    def test_origin_rejected(self):self.assertEqual(self.request('/api/overview',headers={'Origin':'https://evil.example'})[0],403)
    def test_csp_present(self):self.assertIn("script-src 'self'",self.request('/')[2]['Content-Security-Policy'])
    def test_initialize_negotiates(self):
        code,data,_=self.rpc('initialize',{'protocolVersion':'2026-07-28','capabilities':{},'clientInfo':{'name':'fixture','version':'1'}})
        self.assertEqual(code,200);self.assertEqual(data['result']['protocolVersion'],'2025-11-25')
    def test_notification_202_no_body(self):
        code,data,_=self.request('/mcp',{'jsonrpc':'2.0','method':'notifications/initialized'},'mcp');self.assertEqual(code,202);self.assertEqual(data,'')
    def test_unknown_rpc_method(self):self.assertEqual(self.rpc('no_such_method')[1]['error']['code'],-32601)
    def test_tools_real_read_only(self):
        tools=self.rpc('tools/list')[1]['result']['tools'];self.assertGreaterEqual(len(tools),10);self.assertTrue(all(t['annotations']['readOnlyHint'] for t in tools));self.assertNotIn('abort',[t['name'] for t in tools])
    def test_bad_tool_arguments(self):
        d=self.rpc('tools/call',{'name':'list_agents','arguments':{'limit':-1}})[1];self.assertEqual(d['error']['code'],-32602)
    def test_unknown_tool(self):self.assertEqual(self.rpc('tools/call',{'name':'no-tool'})[1]['error']['code'],-32602)
    def test_overview_structured(self):
        data=self.rpc('tools/call',{'name':'mission_overview','arguments':{}})[1]['result'];self.assertFalse(data['isError']);self.assertEqual(data['structuredContent']['verified_active'],0)
    def test_get_mcp_not_fake_sse(self):self.assertEqual(self.request('/mcp',token='mcp')[0],405)
    def test_resource_read(self):self.assertIn('contents',self.rpc('resources/read',{'uri':'mission://overview'})[1]['result'])
    def test_reporting_write_hint_after_enable(self):
        cfg=self.e.config();cfg['enable_reporting']=True;self.e.save_config(cfg)
        tools=self.rpc('tools/list')[1]['result']['tools'];tool=next(t for t in tools if t['name']=='report_event');self.assertFalse(tool['annotations']['readOnlyHint'])
    def test_mcp_cannot_abort_via_api(self):self.assertEqual(self.request('/api/abort',{'session_id':'s','confirm':'s'},'mcp')[0],403)
    def test_invalid_config_not_saved(self):
        old=self.e.config();bad=dict(old,poll_seconds=-1);self.assertEqual(self.request('/api/config',bad)[0],400);self.assertEqual(self.e.config(),old)
    def test_health_identifies_app(self):self.assertEqual(self.request('/health',token=None)[1]['application'],'opencode-mission-control')
    def test_gui_python_uses_console_stdio(self):
        with patch.object(m.sys,'executable','/fixture/pythonw.exe'):
            code,info,_=self.request('/api/integrations')
        self.assertEqual(code,200);self.assertIn(json.dumps(str(Path('/fixture/python.exe'))),info['stdio_toml']);self.assertNotIn('pythonw.exe',info['stdio_toml'])
    def test_mcp_cannot_stop_observer(self):
        self.assertEqual(self.request('/api/shutdown',{'confirm':'STOP OBSERVER'},'mcp')[0],403)
    def test_stop_requires_confirmation(self):
        self.assertEqual(self.request('/api/shutdown',{})[0],400)
    def test_malformed_json_rejected(self):
        req=Request(self.url+'/mcp',data=b'{',headers={'Authorization':'Bearer '+self.e.mcp_token,'Content-Type':'application/json'})
        with self.assertRaises(HTTPError) as cx:self.http.open(req)
        self.assertEqual(cx.exception.code,400)
    def test_oauth_off_by_default(self):self.assertEqual(self.request('/.well-known/oauth-protected-resource',token=None)[0],403)
    def setup_oauth(self):
        cfg=self.e.config();cfg['public_origin']='https://mc.example.test';self.e.save_config(cfg)
        data={'client_name':'Fixture client','redirect_uris':['https://chatgpt.com/connector_platform_oauth_redirect'],'token_endpoint_auth_method':'none'}
        code,client,_=self.request('/oauth/register',data,token=None);self.assertEqual(code,201);return client
    def flow(self,client):
        verifier='v'*64;challenge=base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
        args={'client_id':client['client_id'],'redirect_uri':client['redirect_uris'][0],'resource':'https://mc.example.test/mcp','response_type':'code','code_challenge_method':'S256','code_challenge':challenge,'scope':'mission:read','state':'csrfstate'}
        fid,_,_=self.srv.oauth.begin(args);redirect=self.srv.oauth.approve(fid,self.e.pairing_key);code=parse_qs(urlparse(redirect).query)['code'][0]
        return {'grant_type':'authorization_code','code':code,'client_id':client['client_id'],'redirect_uri':client['redirect_uris'][0],'resource':'https://mc.example.test/mcp','code_verifier':verifier}
    def test_oauth_metadata(self):
        self.setup_oauth();data=self.request('/.well-known/oauth-authorization-server',token=None)[1];self.assertIn('S256',data['code_challenge_methods_supported']);self.assertTrue(data['authorization_response_iss_parameter_supported'])
    def test_oauth_callback_allowlist(self):
        self.setup_oauth();code,_,_=self.request('/oauth/register',{'redirect_uris':['https://evil.test/callback']},token=None);self.assertEqual(code,400)
    def test_oauth_pkce_correct(self):
        client=self.setup_oauth();args=self.flow(client);code,tokens,_=self.request('/oauth/token',args,token=None,form=True);self.assertEqual(code,200)
        self.assertEqual(self.rpc('tools/list',token=tokens['access_token'])[0],200)
        self.assertEqual(self.request('/api/config',token=tokens['access_token'])[0],403)
    def test_oauth_pkce_wrong(self):
        args=self.flow(self.setup_oauth());args['code_verifier']='z'*64;self.assertEqual(self.request('/oauth/token',args,token=None,form=True)[0],400)
    def test_oauth_code_single_use(self):
        args=self.flow(self.setup_oauth());self.assertEqual(self.request('/oauth/token',args,token=None,form=True)[0],200);self.assertEqual(self.request('/oauth/token',args,token=None,form=True)[0],400)
    def test_oauth_audience_bound(self):
        args=self.flow(self.setup_oauth());args['resource']='https://wrong.test/mcp';self.assertEqual(self.request('/oauth/token',args,token=None,form=True)[0],400)
    def test_oauth_refresh_rotates(self):
        client=self.setup_oauth();args=self.flow(client);tokens=self.request('/oauth/token',args,token=None,form=True)[1]
        refresh={'grant_type':'refresh_token','refresh_token':tokens['refresh_token'],'client_id':client['client_id'],'resource':'https://mc.example.test/mcp'}
        self.assertEqual(self.request('/oauth/token',refresh,token=None,form=True)[0],200);self.assertEqual(self.request('/oauth/token',refresh,token=None,form=True)[0],400)
    def test_oauth_revoke(self):
        args=self.flow(self.setup_oauth());tokens=self.request('/oauth/token',args,token=None,form=True)[1];self.srv.oauth.revoke(tokens['access_token']);self.assertEqual(self.rpc('ping',token=tokens['access_token'])[0],401)
    def test_oauth_read_scope_cannot_report(self):
        cfg=self.e.config();cfg['enable_reporting']=True;self.e.save_config(cfg);args=self.flow(self.setup_oauth());tokens=self.request('/oauth/token',args,token=None,form=True)[1]
        d=self.rpc('tools/call',{'name':'report_event','arguments':{'event_id':'e','session_id':'s','source':'chatgpt'}},token=tokens['access_token'])[1]
        self.assertTrue(d['result']['isError']);self.assertEqual(self.e.store.reports(),[])
    def test_oauth_challenge(self):
        self.setup_oauth();status,_,headers=self.rpc('ping',token=None);self.assertEqual(status,401);self.assertIn('resource_metadata',headers['WWW-Authenticate'])
    def test_stdio_bridge_stdout_clean(self):
        runtime={'port':self.port};(self.e.store.directory/'runtime.json').write_text(json.dumps(runtime))
        requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2025-11-25','clientInfo':{'name':'stdio-test'},'capabilities':{}}},{'jsonrpc':'2.0','method':'notifications/initialized'},{'jsonrpc':'2.0','id':2,'method':'tools/list'}]
        p=subprocess.run([sys.executable,str(FILE),'--mcp-stdio','--state-dir',str(self.e.store.directory)],input=''.join(json.dumps(r)+'\n' for r in requests),text=True,capture_output=True,timeout=15)
        self.assertEqual(p.returncode,0,p.stderr);lines=p.stdout.splitlines();self.assertEqual(len(lines),2);self.assertEqual(json.loads(lines[1])['id'],2)


if __name__=='__main__':unittest.main(verbosity=2)
