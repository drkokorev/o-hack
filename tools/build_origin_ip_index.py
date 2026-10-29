"""Derive a small local departure-city index from DB-IP Lite (CC BY 4.0).

python -m tools.build_origin_ip_index --source city.mmdb.gz --release 2026-10
The full city download is a build input, never requested while a visitor uses the app.
"""
import argparse
import gzip
import hashlib
import ipaddress
import json
from pathlib import Path
import maxminddb

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--source',type=Path,required=True)
    parser.add_argument('--release',required=True)
    args=parser.parse_args()
    from domains.trips.geo import ORIGINS
    from apps.location import DATABASE, DATA
    cities=[o.name for o in ORIGINS]
    aliases={name.casefold():i for i,o in enumerate(ORIGINS) for name in [o.name,o.en] if name}
    # The seven original origins predate the English-name field.
    for english,russian in {'moscow':'Москва','saint petersburg':'Санкт-Петербург','st petersburg':'Санкт-Петербург',
        'kazan':'Казань','yekaterinburg':'Екатеринбург','ekaterinburg':'Екатеринбург','novosibirsk':'Новосибирск',
        'nizhny novgorod':'Нижний Новгород','samara':'Самара'}.items():
        if russian in cities:aliases[english]=cities.index(russian)
    ranges={4:[],6:[]};walked=0
    with gzip.open(args.source,'rb') as stream:
        city=maxminddb.open_database(stream,maxminddb.MODE_FD)
    with gzip.open(DATABASE,'rb') as stream:
        country=maxminddb.open_database(stream,maxminddb.MODE_FD)
    for block,record in country:
        if record.get('country',{}).get('iso_code')!='RU':continue
        cursor,limit=int(block.network_address),int(block.broadcast_address)
        while cursor<=limit:
            address=ipaddress.ip_address(cursor) if block.version==4 else ipaddress.IPv6Address(cursor)
            record,prefix=city.get_with_prefix_len(address)
            subnet=ipaddress.ip_network(f'{address}/{prefix}',strict=False)
            end=min(limit,int(subnet.broadcast_address));assert end>=cursor
            walked+=1
            if record and record.get('country',{}).get('iso_code')=='RU':
                names=record.get('city',{}).get('names',{})
                index=next((aliases[names[lang].casefold()] for lang in ['ru','en'] if lang in names and names[lang].casefold() in aliases),None)
                if index is not None:ranges[block.version].append([cursor,end,index])
            cursor=end+1
    city.close();country.close()
    for version,rows in ranges.items():
        rows.sort();merged=[]
        for row in rows:
            if merged and row[0]<=merged[-1][1]:raise ValueError('Overlapping source ranges')
            if merged and row[0]==merged[-1][1]+1 and row[2]==merged[-1][2]:merged[-1][1]=row[1]
            else:merged.append(row)
        ranges[version]=merged
    result={'source':'DB-IP City Lite','release':args.release,'url':'https://db-ip.com/db/download/ip-to-city-lite',
        'license':'CC BY 4.0','source_sha256':hashlib.sha256(args.source.read_bytes()).hexdigest(),
        'cities':cities,'ipv4':ranges[4],'ipv6':ranges[6]}
    out=DATA/'origin-ip-index.json.gz'
    out.write_bytes(gzip.compress(json.dumps(result,ensure_ascii=False,separators=(',',':')).encode(),mtime=0))
    print(json.dumps({'bytes':out.stat().st_size,'ipv4_ranges':len(ranges[4]),'ipv6_ranges':len(ranges[6]),'source_ranges_visited':walked,'covered_cities':len({r[2] for rows in ranges.values() for r in rows})}))

if __name__=='__main__':main()
