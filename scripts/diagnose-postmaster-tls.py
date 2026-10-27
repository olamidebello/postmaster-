#!/usr/bin/env python3
"""Read-only listener/routing/certificate report. Never prints private keys."""
import json,pathlib,re,subprocess,time
REPORT=pathlib.Path('/var/lib/postmaster-https-repair')
def run(argv,data=None):
    try:
        p=subprocess.run(argv,input=data,capture_output=True,text=True,timeout=15)
        return {'rc':p.returncode,'stdout':p.stdout,'stderr':p.stderr}
    except (OSError,subprocess.TimeoutExpired) as e:return {'rc':-1,'error':str(e)}
def main():
    raw=run(['nginx','-T']);file='';directives=[]
    for line in raw.get('stdout','').splitlines():
        if line.startswith('# configuration file '):file=line[len('# configuration file '):].rstrip(':')
        if re.match(r'\s*(listen|server_name|ssl_certificate)\s',line):directives.append({'file':file,'directive':line.strip()})
    listeners=run(['ss','-ltnp','( sport = :443 )'])
    certificates={}
    for addr in ('127.0.0.1:443','[::1]:443'):
        # s_client retrieves the public certificate for diagnosis only. This
        # neither authorizes requests nor replaces the strict verification task.
        response=run(['openssl','s_client','-connect',addr,'-servername','postmaster.justisolve.com','-showcerts'],'')
        match=re.search(r'-----BEGIN CERTIFICATE-----.*?-----END CERTIFICATE-----',response.get('stdout',''),re.S)
        certificates[addr]=run(['openssl','x509','-noout','-subject','-issuer','-dates','-ext','subjectAltName'],match.group(0)) if match else {'error':'No peer certificate','detail':response.get('stderr',response.get('error',''))}
    expected=run(['openssl','x509','-in','/etc/letsencrypt/live/postmaster-justisolve-com/fullchain.pem','-noout','-subject','-issuer','-dates','-ext','subjectAltName'])
    result={'time':int(time.time()),'nginx_rc':raw['rc'],'nginx_stderr':raw.get('stderr',''),'listeners_443':listeners,'routing_directives':directives,'served_certificates':certificates,'expected_certificate':expected}
    REPORT.mkdir(parents=True,exist_ok=True,mode=0o700)
    dest=REPORT/'diagnostics.json';dest.write_text(json.dumps(result,indent=2)+'\n');dest.chmod(0o600)
    print(json.dumps(result,indent=2));print('Diagnostics saved to '+str(dest))
if __name__=='__main__':main()
