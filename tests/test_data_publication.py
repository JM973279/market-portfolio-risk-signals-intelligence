"""Reproduce two independent Actions data writers without external network."""
import os
from pathlib import Path
import subprocess
import tempfile
import unittest

SCRIPT = Path(__file__).resolve().parents[1]/'scripts/push_data_commit.sh'


class DataPublicationTest(unittest.TestCase):
    def git(self, folder, *args, check=True):
        return subprocess.run(['git', '-C', str(folder), *args], check=check,
                              capture_output=True, text=True)

    def setup_repos(self, root):
        remote=root/'remote.git';first=root/'first';second=root/'second'
        subprocess.run(['git','init','--bare','--initial-branch=main',str(remote)],check=True,capture_output=True)
        subprocess.run(['git','clone',str(remote),str(first)],check=True,capture_output=True)
        self.configure(first)
        (first/'shared.txt').write_text('seed\n')
        self.git(first,'add','.');self.git(first,'commit','-m','seed');self.git(first,'push','origin','main')
        subprocess.run(['git','clone',str(remote),str(second)],check=True,capture_output=True)
        self.configure(second)
        return remote,first,second

    def configure(self, folder):
        self.git(folder,'config','user.email','test@example.invalid')
        self.git(folder,'config','user.name','test')
        self.git(folder,'config','commit.gpgsign','false')

    def test_parallel_disjoint_data_commits_are_both_preserved(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote,a,b=self.setup_repos(Path(tmp))
            (a/'korea.txt').write_text('new korea data\n')
            self.git(a,'add','.');self.git(a,'commit','-m','korea');self.git(a,'push','origin','main')
            (b/'portfolio.txt').write_text('new portfolio data\n')
            self.git(b,'add','.');self.git(b,'commit','-m','portfolio')
            p=subprocess.run(['bash',str(SCRIPT)],cwd=b,capture_output=True,text=True)
            self.assertEqual(p.returncode,0,p.stderr)
            self.assertEqual(self.git(remote,'show','main:korea.txt').stdout,'new korea data\n')
            self.assertEqual(self.git(remote,'show','main:portfolio.txt').stdout,'new portfolio data\n')

    def test_same_path_conflict_never_overwrites_remote(self):
        with tempfile.TemporaryDirectory() as tmp:
            remote,a,b=self.setup_repos(Path(tmp))
            (a/'shared.txt').write_text('first update\n')
            self.git(a,'add','.');self.git(a,'commit','-m','first');self.git(a,'push','origin','main')
            head=self.git(remote,'rev-parse','main').stdout
            (b/'shared.txt').write_text('second update\n')
            self.git(b,'add','.');self.git(b,'commit','-m','second')
            p=subprocess.run(['bash',str(SCRIPT)],cwd=b,capture_output=True,text=True)
            self.assertNotEqual(p.returncode,0)
            self.assertEqual(self.git(remote,'rev-parse','main').stdout,head)
            self.assertEqual(self.git(remote,'show','main:shared.txt').stdout,'first update\n')
