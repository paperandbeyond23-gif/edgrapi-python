# -*- coding: utf-8 -*-
"""Command line entry point: ``edgrapi <command> [args]``.

Exists so the package can be tried in one line without writing any Python::

    pip install edgrapi
    export EDGRAPI_KEY=edgr_...
    edgrapi holdings berkshire --changes

Prints JSON to stdout so it composes with ``jq``. Diagnostics go to stderr, so
piping stays clean.
"""
import argparse
import json
import sys

from . import Client, EdgrapiError, OutOfCredits, RateLimited, __version__

# command -> (client method, path args, allowed options)
COMMANDS = {
    "company":        ("company", ["ticker"], []),
    "filings":        ("filings", ["ticker"], ["form", "limit"]),
    "resolve":        ("resolve", [], ["ticker", "cik", "cusip"]),
    "subsidiaries":   ("subsidiaries", ["ident"], []),
    "fundamentals":   ("fundamentals", ["ticker"], ["period", "limit"]),
    "ratios":         ("ratios", ["ticker"], []),
    "xbrl":           ("xbrl", ["ident"], ["period", "limit", "concept"]),
    "shares":         ("shares", ["ticker"], ["history"]),
    "sections":       ("sections", ["ticker"], ["form", "item"]),
    "insider":        ("insider", ["ticker"], ["limit", "form", "min_value", "days", "min_insiders"]),
    "clusters":       ("clusters", [], ["days", "min_insiders", "min_value", "limit"]),
    "form144":        ("form144", ["ticker"], ["limit"]),
    "events":         ("events", ["ticker"], ["limit", "notable", "item"]),
    "restatements":   ("restatements", [], ["limit", "days"]),
    "auditor-changes": ("auditor_changes", [], ["limit", "days"]),
    "activist":       ("activist", ["identifier?"], ["activist_only", "min_percent", "limit"]),
    "holdings":       ("holdings", ["identifier"], ["limit", "changes"]),
    "formd":          ("formd", ["ident?"], ["limit"]),
    "search":         ("search", ["q"], ["forms", "startdt", "enddt", "limit", "offset"]),
}

_INT = {"limit", "offset", "days", "min_insiders", "min_value"}
_BOOL = {"notable", "changes", "history", "activist_only"}


def _build_parser():
    p = argparse.ArgumentParser(
        prog="edgrapi",
        description="SEC EDGAR filings as clean JSON. Free key: https://edgrapi.com/app",
        epilog="Examples:\n"
               "  edgrapi holdings berkshire --changes\n"
               "  edgrapi clusters --days 15 --min-insiders 3\n"
               "  edgrapi insider AAPL --limit 5 | jq '.transactions[0]'\n"
               "  edgrapi search 'climate risk' --forms 10-K",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("--version", action="version", version="edgrapi %s" % __version__)
    p.add_argument("--key", help="API key (default: $EDGRAPI_KEY)")
    p.add_argument("--base-url", default=None, help="override the API host")
    p.add_argument("--raw", action="store_true", help="print compact JSON, no indent")
    p.add_argument("--quiet", "-q", action="store_true", help="suppress the credit line on stderr")

    sub = p.add_subparsers(dest="command", metavar="<command>")
    for name, (_m, path_args, opts) in COMMANDS.items():
        sp = sub.add_parser(name, help=None)
        for a in path_args:
            if a.endswith("?"):
                sp.add_argument(a[:-1], nargs="?", default="latest")
            else:
                sp.add_argument(a)
        for o in opts:
            flag = "--" + o.replace("_", "-")
            if o in _BOOL:
                sp.add_argument(flag, action="store_true", default=None)
            elif o in _INT:
                sp.add_argument(flag, type=int, default=None)
            else:
                sp.add_argument(flag, default=None)
    return p


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)

    if not args.command:
        parser.print_help()
        return 0

    method_name, path_args, opts = COMMANDS[args.command]
    positional = [getattr(args, a.rstrip("?")) for a in path_args]
    kwargs = {o: getattr(args, o) for o in opts if getattr(args, o, None) is not None}

    try:
        kw = {}
        if args.base_url:
            kw["base_url"] = args.base_url
        client = Client(args.key, **kw)
        result = getattr(client, method_name)(*positional, **kwargs)
    except ValueError as e:
        print("error: %s" % e, file=sys.stderr)
        return 2
    except OutOfCredits as e:
        print("out of credits (this call costs %s). See https://edgrapi.com/pricing"
              % (e.endpoint_cost if e.endpoint_cost is not None else "?"), file=sys.stderr)
        return 4
    except RateLimited as e:
        hint = " retry after %ss." % e.retry_after if e.retry_after else ""
        print("rate limited.%s" % hint, file=sys.stderr)
        return 5
    except EdgrapiError as e:
        print("error: %s" % e, file=sys.stderr)
        return 3

    json.dump(result, sys.stdout, indent=None if args.raw else 2, default=str)
    sys.stdout.write("\n")

    if not args.quiet and result.credits_cost is not None:
        rem = result.credits_remaining
        print("cost %s credit%s%s" % (
            result.credits_cost,
            "" if result.credits_cost == 1 else "s",
            "" if rem is None else ", %s remaining" % rem,
        ), file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
