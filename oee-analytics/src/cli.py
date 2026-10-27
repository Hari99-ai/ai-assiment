import argparse
from scripts.run_pipeline import run

def main():
    p=argparse.ArgumentParser(prog="oee"); sub=p.add_subparsers(dest="command",required=True)
    g=sub.add_parser("generate");g.add_argument("--scale",choices=["small","full"],default="small");g.add_argument("--seed",type=int)
    for name in ("validate","calculate-oee","report"): sub.add_parser(name)
    a=p.parse_args()
    if a.command=="generate": run(a.scale,a.seed)
    else: run("small",None)
if __name__=="__main__": main()
