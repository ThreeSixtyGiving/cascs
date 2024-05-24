import argparse
import csv
import hashlib
import io
import json
import re
import unicodedata
from collections import defaultdict

from pyexcel_ods3 import get_data
from requests_html import HTMLSession
from utils import to_titlecase

CASC_BASE = "https://www.gov.uk/government/publications/community-amateur-sports-clubs-casc-registered-with-hmrc--2"
CASC_ID_LOOKUP = "cascs_id_lookup.csv"
CASC_ORG_ID_PREFIX = "GB-CASC"
RECORD_KEYS = ["name", "address", "postcode", "active"]


with open(CASC_ID_LOOKUP, "r") as f:
    id_lookups = {
        r["new_id"]: r["old_id"]
        for r in csv.DictReader(f)
        if r["new_id"] != r["old_id"]
    }
    for k, v in list(id_lookups.items()):
        id_lookups[v] = k


def normalizeString(s: str):
    s = s.lower()
    s = re.sub(r"[.,(){}\[\]-]", " ", s)
    s = re.sub(r"[^0-9a-z ]", "", s)
    s = s.strip()
    s = re.sub(r"^the\b", "", s)
    s = re.sub(r"\b(ltd|limited)$", "", s)
    s = re.sub(r"\b&\b", " and ", s)
    s = re.sub(r"\bc[ \.]?i[ \.]?c[ \.]?$", " cic", s)
    s = re.sub(r" +", " ", s)
    s = unicodedata.normalize("NFC", s)
    s = s.strip()
    return s


def get_org_id(record, org_id_prefix=CASC_ORG_ID_PREFIX):
    """
    CASCs don't come with a ID, so we're creating a dummy one.
    This is defined by:
    1. Put together the name of the club + the postcode (or the string None if there is no postcode)
    2. Take the MD5 hash of the utf8 representation of this string
    3. Use the first 8 characters of the hexdigest of this hash
    """

    def hash_id(w):
        return hashlib.md5(w.encode("utf8")).hexdigest()[0:8]

    return "-".join(
        [org_id_prefix, hash_id(str(record["name"]) + str(record["postcode"]))]
    )


def fetch_cascs(
    casc_url=CASC_BASE, org_id_prefix=CASC_ORG_ID_PREFIX, existing_casc_ids: set = set()
):
    session = HTMLSession()

    r = session.get(CASC_BASE)
    ids_seen = set()

    for link in r.html.absolute_links:
        if not link.endswith(".ods"):
            continue
        print(link)
        p = session.get(link)

        data = get_data(io.BytesIO(p.content))
        headers = None
        first_sheet = list(data.keys())[0]
        for row in data[first_sheet]:
            if len(row) <= 5 and len(row) > 0:
                # pad row array out to 5 elements
                row += [""] * (5 - len(row))
            if headers is None:
                headers = row
                continue
            record = {k: v.strip() for k, v in zip(headers, row) if k and v}
            record = {
                "name": to_titlecase(record.get("Organisation Name")),
                "address": ", ".join(
                    [v for k, v in record.items() if k.startswith("Address") and v]
                ),
                "postcode": record.get("Postcode"),
            }
            if record["name"] is None:
                continue
            record["id"] = get_org_id(record, org_id_prefix)
            record_id = record["id"]
            row_ids_seen = set()
            while True:
                if record_id in id_lookups:
                    record_id = id_lookups.get(record_id)
                    if record_id in row_ids_seen:
                        break
                    row_ids_seen.add(record_id)
                else:
                    break

            for id in row_ids_seen:
                if id in existing_casc_ids:
                    record["id"] = id
                    break

            if record["id"] in ids_seen:
                continue
            yield record
            ids_seen.add(record["id"])


def main():
    parser = argparse.ArgumentParser(
        description="Extract a list of Community Amateur Sports Clubs from HMRC and add a unique identifier"
    )
    parser.add_argument(
        "infile",
        type=argparse.FileType("r", encoding="UTF-8"),
        help="Existing cascs file to merge with",
    )
    parser.add_argument(
        "outfile",
        type=str,
        nargs="+",
        help="Destination file for the data",
    )
    parser.add_argument(
        "--name-match",
        help="Instead of updating the data produce a list of name matches",
    )
    parser.add_argument("--url", default=CASC_BASE, help="URL to fetch from")
    parser.add_argument(
        "--prefix", default=CASC_ORG_ID_PREFIX, help="Prefix to use for org ids"
    )
    args = parser.parse_args()

    existing_cascs = {}
    if args.infile.name.endswith("csv"):
        reader = csv.DictReader(args.infile)
        existing_cascs = {r["id"]: {**r, "active": False} for r in reader}
        print(f"Loaded {len(existing_cascs)} existing cascs")
    elif args.infile.name.endswith("json"):
        existing_cascs = {
            r["id"]: {**r, "active": False} for r in json.load(args.infile)["cascs"]
        }
        print(f"Loaded {len(existing_cascs)} existing cascs")
    args.infile.close()

    cascs = {
        **existing_cascs,
        **{
            c["id"]: {**c, "active": True}
            for c in fetch_cascs(
                args.url,
                args.prefix,
                existing_casc_ids={
                    existing_casc["id"] for existing_casc in existing_cascs.values()
                },
            )
        },
    }
    cascs = sorted(list(cascs.values()), key=lambda x: x.get("name", x.get("id")))
    print(f"Found {len(cascs)} cascs")

    if args.name_match:
        name_match = defaultdict(set)
        for c in cascs:
            name_match[normalizeString(c["name"])].add(c["id"])

        with open("name_match.csv", "w") as f:
            writer = csv.DictWriter(
                f, fieldnames=["id1", "id2", "name"], lineterminator="\n"
            )
            writer.writeheader()
            for k, v in name_match.items():
                if len(v) == 2:
                    writer.writerow({"id1": list(v)[0], "id2": list(v)[1], "name": k})

    else:
        for filename in args.outfile:
            with open(filename, "w", encoding="UTF-8") as f:
                if filename.endswith("csv"):
                    writer = csv.DictWriter(
                        f, fieldnames=["id"] + RECORD_KEYS, lineterminator="\n"
                    )
                    writer.writeheader()
                    writer.writerows(cascs)
                elif filename.endswith("json"):
                    json.dump({"cascs": cascs}, f, indent=4)

            f.close()


if __name__ == "__main__":
    main()
