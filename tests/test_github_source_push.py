from pathlib import Path
import subprocess
import pytest
from tools import push_github_source as publisher


@pytest.fixture
def repo(tmp_path):
    def run(*args):return subprocess.run(['git','-C',str(tmp_path),*args],check=True,capture_output=True,text=True)
    run('init','-b',publisher.EXPECTED_BRANCH)
    run('config','user.name','Synthetic Test');run('config','user.email','synthetic@example.test')
    run('remote','add','origin','https://github.com/Ravi-ranjan-kumar-dev/telecom_forensics_analysis_suite.git')
    (tmp_path/'modules').mkdir();(tmp_path/'modules/example.py').write_text('VALUE = 1\n')
    (tmp_path/'.env').write_text('SECRET=synthetic-private-value\n')
    (tmp_path/'database').mkdir();(tmp_path/'database/private.duckdb').write_bytes(b'synthetic evidence')
    return tmp_path,run


def test_only_source_committed_and_remote_push_is_explicit(repo,monkeypatch):
    path,run=repo;original=publisher.git;pushes=[]
    def fake(project,*args,**kwargs):
        if args[0]=='push':
            pushes.append(args);return subprocess.CompletedProcess(args,0,'synthetic push suppressed','')
        return original(project,*args,**kwargs)
    monkeypatch.setattr(publisher,'git',fake)
    publisher.publish(path,push=True)
    assert set(run('ls-files').stdout.splitlines())=={'.gitignore','modules/example.py'}
    assert pushes==[('push','-u','origin','HEAD:refs/heads/'+publisher.EXPECTED_BRANCH)]
    assert (path/'database/private.duckdb').read_bytes()==b'synthetic evidence'
    assert 'synthetic-private-value' in (path/'.env').read_text()


def test_plan_does_not_stage_or_change_ignore(repo):
    path,run=repo;publisher.publish(path)
    assert not (path/'.gitignore').exists()
    assert not run('diff','--cached','--name-only').stdout


def test_tracked_secret_blocks_commit(repo):
    path,run=repo;run('add','.env')
    with pytest.raises(ValueError,match='runtime/secret'):publisher.publish(path,push=True)
    assert not (path/'.gitignore').exists()


def test_unexpected_branch_blocks_push(repo):
    path,run=repo;run('symbolic-ref','HEAD','refs/heads/other-branch')
    with pytest.raises(ValueError,match='Unexpected branch'):publisher.publish(path,push=True)
    assert not (path/'.gitignore').exists()
