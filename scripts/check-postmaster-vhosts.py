#!/usr/bin/env python3
"""Refuse competing exact hostname declarations; do not edit unrelated vhosts."""
import pathlib,re,subprocess,sys
DOMAIN='postmaster.justisolve.com'
MANAGED=pathlib.Path('/etc/nginx/sites-available/postmaster-'+DOMAIN)
def conflicts(dump):
    current=None;bad=set()
    for part in re.split(r'(?m)^# configuration file (.+):\s*$',dump)[1:]:
        if current is None:current=part.strip();continue
        clean=re.sub(r'(?m)#.*$','',part)
        for directive in re.findall(r'\bserver_name\s+([^;]+);',clean):
            names=[x.strip('\"\'') for x in directive.split()]
            if DOMAIN in names and pathlib.Path(current).resolve()!=MANAGED.resolve():bad.add(current)
        current=None
    return sorted(bad)
def main():
    result=subprocess.run(['nginx','-T'],capture_output=True,text=True)
    if result.returncode:raise SystemExit('nginx -T failed; fix the existing configuration first:\n'+result.stderr)
    bad=conflicts(result.stdout)
    if bad:raise SystemExit('Competing exact Postmaster hostname found. No files changed. Consolidate these declarations into '+str(MANAGED)+':\n'+'\n'.join(bad))
    print('No competing exact Postmaster hostname; unrelated sites retained')
if __name__=='__main__':main()
