"""Safe local-only developer bootstrap; not for deployment."""
import os
import secrets
import argparse


def main():
    parser=argparse.ArgumentParser(description='Start local developer instance with ephemeral operator credentials')
    parser.add_argument('--port',type=int,default=8000)
    args=parser.parse_args()
    os.environ.setdefault('GRAND_ADMIN_PASSWORD',secrets.token_urlsafe(18))
    os.environ.setdefault('GRAND_SESSION_SECRET',secrets.token_urlsafe(48))
    os.environ.setdefault('GRAND_DB_PATH','data/dev-support.sqlite3')
    os.environ.setdefault('GRAND_UPLOAD_DIR','data/dev-uploads')
    print('\nGrand Mobile × Outsiders — LOCAL TEST ONLY')
    print('Player: http://127.0.0.1:%d/' % args.port)
    print('Operator: http://127.0.0.1:%d/admin' % args.port)
    print('Operator password: '+os.environ['GRAND_ADMIN_PASSWORD'])
    print('Do not expose this development server on a public network.\n',flush=True)
    import uvicorn
    uvicorn.run('app.api:app',host='127.0.0.1',port=args.port,access_log=False)


if __name__=='__main__':main()
