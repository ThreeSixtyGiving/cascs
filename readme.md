# Community Amateur Sports Clubs

This project creates and stores a list of [Community Amateur Sports Clubs (CASC)](https://www.gov.uk/topic/community-organisations/community-amateur-sports-clubs), a type of non profit organisation registered in the UK with HMRC.

It takes the [list of clubs published by HMRC](https://www.gov.uk/government/publications/community-amateur-sports-clubs-casc-registered-with-hmrc--2) and turns it into a consistently formated CSV or JSON data. It also adds a unique identifier for each club, which is based on the name and address of the club.

## Org ID

The reason for adding a unique identifier is to allow CASCs to be listed in  the [org ID scheme](http://org-id.guide/) for Organisation Identifiers.

Because HMRC do not make the identifiers for these organisations public, we have to create one. This identifier is not ideal as it is based on the name and postcode of the club, so will change when either of those change.

[This issue contains discussion about the reasons for creating this repository](https://github.com/org-id/register/issues/361)

## Function to create an identifier

The identifier is created in [cascs/fetch_cascs.py](cascs/fetch_cascs.py#L13-L28). The function does the following:

1. Concatenate the name and postcode of the record (name first). If either is null then replace with the string `None`. Both strings must be UTF-8 encoded.
2. Take the MD5 hash of the concatenated string.
3. Get the hexdigest of the hash.
4. The first 8 characters of the hexdigest becomes the ID for the record
5. Add `GB-CASC-` as a prefix to create an OrgID-compliant identifier.

In this package this is implented using python's [hashlib](https://docs.python.org/3/library/hashlib.html) library.

## Running the script

To create a CSV file with the contents of the HMRC list of registered cascs run the following command:

```sh
python cascs /path/to/file.csv
```

To create a JSON file with the same data run:

```sh
python cascs /path/to/file.json
```

To create both files run:

```sh
python cascs /path/to/file.csv /path/to/file.json
```

The full process to update the CSV and JSON files in this repository should be something like:

```sh
python cascs cascs.csv cascs.json
git add cascs.csv
git commit -m 'Add new cascs'
git push origin master
```

## CASCs registered with Companies House

The file [casc_company_house.csv](casc_company_house.csv) contains a list of CASCs that also appear to be registered with Companies House (based on matching the name). This file is manually created by matching the name of the CASC with the name on Companies House (replacing 'Ltd' with 'Limited' where appropriate, and ignoring the case).
