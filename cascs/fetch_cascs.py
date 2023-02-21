import argparse
import csv
import hashlib
import io
import json
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
        **{r["new_id"]: r["old_id"] for r in csv.DictReader(f)},
    }


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


def fetch_cascs(casc_url=CASC_BASE, org_id_prefix=CASC_ORG_ID_PREFIX):
    session = HTMLSession()

    r = session.get(CASC_BASE)
    ids_seen = set()

    for l in r.html.absolute_links:
        if not l.endswith(".ods"):
            continue
        print(l)
        p = session.get(l)

        data = get_data(io.BytesIO(p.content))
        headers = None
        first_sheet = list(data.keys())[0]
        for row in data[first_sheet]:
            if len(row) <= 5:
                continue
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
            record["id"] = get_org_id(record, org_id_prefix)
            record["id"] = id_lookups.get(record["id"], record["id"])

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
        **{c["id"]: {**c, "active": True} for c in fetch_cascs(args.url, args.prefix)},
    }
    cascs = sorted(list(cascs.values()), key=lambda x: x.get("name", x.get("id")))
    print(f"Found {len(cascs)} cascs")

    name_match = defaultdict(set)
    for c in cascs:
        name_match[c["name"]].add(c["id"])

    with open("name_match.csv", "w") as f:
        writer = csv.DictWriter(
            f, fieldnames=["id1", "id2", "name"], lineterminator="\n"
        )
        writer.writeheader()
        for k, v in name_match.items():
            if len(v) == 2:
                writer.writerow({"id1": list(v)[0], "id2": list(v)[1], "name": k})

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
