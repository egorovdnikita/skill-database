import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
SOURCE=Path(__file__).resolve().parents[1]

class IntegrationTests(unittest.TestCase):
    def test_separate_repositories(self):
        for name in ['concepts','database']:
            with self.subTest(skill=name), tempfile.TemporaryDirectory() as tmp:
                base=Path(tmp);repo=base/'repo';repo.mkdir();remote=base/'remote.git';home=base/'home';home.mkdir()
                env=dict(os.environ,HOME=str(home))
                def cmd(*args,ok=True):
                    r=subprocess.run(args,cwd=repo,env=env,capture_output=True,text=True)
                    if ok:self.assertEqual(r.returncode,0,r.stderr)
                    return r
                cmd('git','init','--bare',str(remote));cmd('git','init','-b','main')
                cmd('git','config','user.name','Никита Егоров');cmd('git','config','user.email','egorov.d.nikita@mail.ru')
                (repo/'scripts').mkdir();shutil.copyfile(SOURCE/'scripts/sync-skills.py',repo/'scripts/sync-skills.py')
                canonical=repo/'SKILL.md';canonical.write_text(f'---\nname: {name}\ndescription: test\n---\nbase\n')
                mirror=home/f'.claude/skills/synced/bucket/{name}/SKILL.md';mirror.parent.mkdir(parents=True);mirror.write_bytes(canonical.read_bytes())
                # Другой навык не должен читаться или изменяться этим репозиторием.
                other_name='database' if name=='concepts' else 'concepts'
                other=home/f'.claude/skills/synced/bucket/{other_name}/SKILL.md';other.parent.mkdir(parents=True);other.write_text(f'---\nname: {other_name}\n---\nuntouched')
                original_other=other.read_bytes()
                cmd('git','add','.');cmd('git','commit','-m','База теста');cmd('git','remote','add','origin',str(remote));cmd('git','push','origin','main')
                script=str(repo/'scripts/sync-skills.py');cmd('python3','-I',script,'init')
                canonical.write_text(canonical.read_text()+'local\n');cmd('python3','-I',script,'sync');self.assertEqual(canonical.read_bytes(),mirror.read_bytes())
                mirror.write_text(mirror.read_text()+'cloud\n');cmd('python3','-I',script,'sync');self.assertEqual(canonical.read_bytes(),mirror.read_bytes())
                canonical.write_text(canonical.read_text()+'conflict local\n');mirror.write_text(mirror.read_text()+'conflict cloud\n');a,b=canonical.read_bytes(),mirror.read_bytes()
                self.assertNotEqual(cmd('python3','-I',script,'sync',ok=False).returncode,0);self.assertEqual((a,b),(canonical.read_bytes(),mirror.read_bytes()))
                mirror.write_bytes(a);cmd('git','remote','set-url','--push','origin',str(base/'missing.git'))
                self.assertNotEqual(cmd('python3','-I',script,'sync',ok=False).returncode,0)
                cmd('git','remote','set-url','--push','origin',str(remote));cmd('python3','-I',script,'sync')
                self.assertEqual(cmd('git','rev-parse','HEAD').stdout.strip(),cmd('git','--git-dir',str(remote),'rev-parse','main').stdout.strip())
                self.assertEqual(other.read_bytes(),original_other)

if __name__=='__main__':unittest.main()
