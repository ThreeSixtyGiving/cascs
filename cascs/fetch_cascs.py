import argparse
import csv
import hashlib
import json

from requests_html import HTMLSession

CASC_BASE = 'https://www.gov.uk/government/publications/community-amateur-sports-clubs-casc-registered-with-hmrc--2'
CASC_ORG_ID_PREFIX = 'GB-CASC'
RECORD_KEYS = ['name', 'address', 'postcode']


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

    return "-".join([
        org_id_prefix,
        hash_id(str(record["name"])+str(record["postcode"]))
    ])


def fetch_cascs(casc_url=CASC_BASE, org_id_prefix=CASC_ORG_ID_PREFIX):
    session = HTMLSession()

    r = session.get(CASC_BASE)

    for l in r.html.absolute_links:
        if not l.startswith(CASC_BASE):
            continue
        print(l)
        p = session.get(l)
        for table in p.html.find('.govspeak > table'):
            for tr in table.find('tbody > tr'):
                record = dict(zip(RECORD_KEYS, [c.text for c in tr.find('td')]))
                record['id'] = get_org_id(record, org_id_prefix=org_id_prefix)
                yield record


def main():
    parser = argparse.ArgumentParser(description='Extract a list of Community Amateur Sports Clubs from HMRC and add a unique identifier')
    parser.add_argument('outfile', type=argparse.FileType('w', encoding='UTF-8'), nargs='+', help='Destination file for the data')
    parser.add_argument('--url', default=CASC_BASE, help='URL to fetch from')
    parser.add_argument('--prefix', default=CASC_ORG_ID_PREFIX, help='Prefix to use for org ids')
    args = parser.parse_args()

    cascs = {c['id']: c for c in fetch_cascs(args.url, args.prefix)}
    cascs = sorted(list(cascs.values()), key=lambda x: x.get('name', x.get('id')))

    for f in args.outfile:
        if f.name.endswith('csv'):
            writer = csv.DictWriter(f, fieldnames=[
                                    'id'] + RECORD_KEYS, lineterminator='\n')
            writer.writeheader()
            writer.writerows(cascs)
        elif f.name.endswith('json'):
            json.dump({'cascs': cascs}, f, indent=4)

        f.close()


if __name__ == "__main__":
    main()
