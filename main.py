#!/usr/bin/env python
# -*- coding: utf-8 -*-

from copy import copy, deepcopy
from datetime import datetime, timedelta
import icalendar
import locale
import logging
from optparse import OptionParser
import re
import json
import os
import requests
import xml.dom.minidom

URL = 'http://www.06blog.it/categoria/scioperi/rss2.xml'

def create(item, from_date, end_date=None):
    title = item.getElementsByTagName('title')[0].firstChild.data
    link = item.getElementsByTagName('link')[0].firstChild.data

    if not end_date:
        end_date = copy(from_date)

    # make this explicit for easy datetime comparison later on
    from_date = from_date.replace(hour=0, minute=0, second=0)
    end_date = end_date.replace(hour=23, minute=59, second=59)

    logging.debug('saving item')

    return {
        'title': title,
        'link': link,
        'from': from_date,
        'ends': end_date
    }

def parse_date(s):
    logging.info('setting LC_TIME to "it_IT.utf8"')
    locale.setlocale(locale.LC_TIME, 'it_IT.utf8')

    logging.debug('trying to parse date "%s"', s)
    return datetime.strptime(s, '%d %B %Y')

def get_json(scioperi):
    # none of this is great and
    # http://stackoverflow.com/questions/455580/json-datetime-between-python-and-javascript
    # doesn't really give any better suggestions
    scioperi = deepcopy(scioperi)

    for s in scioperi:
        s['from'] = s['from'].isoformat()
        s['ends'] = s['ends'].isoformat()

    return json.dumps(scioperi)

def get_rss():
    logging.debug('making GET request to "%s"', URL)
    r = requests.get(URL)
    data = r.text

    logging.debug('got response "%s..."', data[:30])

    return xml.dom.minidom.parseString(data.encode('utf-8'))

def parse(rss):
    scioperi = []

    logging.info('parsing')

    items = rss.getElementsByTagName('item')
    for item in items:
        logging.debug('new item')

        # we only care about the public transport
        categories = [e.firstChild.data
            for e in item.getElementsByTagName('category')]
        logging.debug('in categories: %s', categories)

        if 'mezzi pubblici' not in categories:
            logging.debug('ignoring item, not about mezzi pubblici')
            continue

        title = item.getElementsByTagName('title')[0].firstChild.data
        content = item.getElementsByTagName('content:encoded')[0]\
            .firstChild.data

        logging.debug('title is "%s"', title)

        # we don't care about coltral or alitalia or other scioperi
        if 'Atac' not in title and 'Atac' not in content:
            logging.debug('ignoring item, item doesn\'t appear to be about Atac')
            continue

        title = title.replace(u'°', '')
        title = title.replace("all'", "al ") # to remove dall'8

        logging.info('matching dates')

        # 1. date ranges

        # 1a. same month
        match = re.search(r'dal (\d{1,2}) al (\d{1,2} \w+ \d{4})', title)
        if match:
            logging.debug('matched same month date range: %s', match.groups())
            end_date = parse_date(match.group(2))

            from_day = int(match.group(1))
            from_date = copy(end_date)
            from_date -= timedelta(days=(end_date.day - from_day))

            scioperi.append(create(item, from_date, end_date))
            continue

        # 1b. different month
        match = re.search(r'dal (\d{1,2} \w+) al (\d{1,2} \w+ \d{4})',
            title)
        if match:
            logging.debug('matched different month date range: %s', match.groups())
            end_date = parse_date(match.group(2))

            from_day = match.group(1) + ' ' + str(end_date.year)
            from_date = parse_date(from_day)

            scioperi.append(create(item, from_date, end_date))
            continue

        # 2. single date
        match = re.search(r'\d{1,2} \w+ \d{4}', title)
        if match:
            logging.debug('matched single date: "%s"', match.group(0))
            date = parse_date(match.group(0))
            scioperi.append(create(item, date))
            continue

        logging.debug('ignoring item, couldn\'t find a date in the title')

    logging.info('finished with item parsing')

    return scioperi

def write_json(basepath, scioperi):
    logging.info('writing json files')

    now = datetime.now()

    def write(filename, items):
        path = os.path.join(basepath, filename)
        with open(path, 'w') as f:
            f.write(get_json(items))

    write('all.json', scioperi)

    write('past.json', [s for s in scioperi if s['ends'] < now])

    write('ongoing.json',
        [s for s in scioperi if s['from'] < now and s['ends'] > now])

    write('future.json', [s for s in scioperi if s['ends'] > now])

    logging.info('finished writing json files')

def write_ical(basepath, scioperi):
    logging.info('making ical file')

    cal = icalendar.Calendar()
    cal.add('prodid', '-//Sciopero//jonnylamb.com//')
    cal.add('version', '2.0')
    cal.add('x-wr-calname', 'Scioperi a Roma')
    cal.add('x-wr-caldesc', 'Gli scioperi dell\'Atac')
    cal.add('x-published-ttl', 'PT23H')

    for item in scioperi:
        e = icalendar.Event()
        e.add('summary', item['title'])
        e.add('dtstart', item['from'].date())
        e.add('dtend', item['ends'].date())
        e.add('description', item['link'])
        cal.add_component(e)

    path = os.path.join(basepath, 'all.ical')
    with open(path, 'w') as f:
        f.write(cal.to_ical())

    logging.info('finished writing ical file')

def main():
    parser = OptionParser()
    parser.add_option('--logfile', dest='logfile', help='path to the logfile',
        default='sciopero.log')
    parser.add_option('--basepath', dest='basepath',
        help='directory in which to save the files', default='.')
    (options, args) = parser.parse_args()

    logging.basicConfig(filename=options.logfile, level=logging.DEBUG,
        format='%(asctime)s - %(levelname)s - %(message)s')

    logging.info('starting')

    rss = get_rss()
    scioperi = parse(rss)

    write_json(options.basepath, scioperi)
    write_ical(options.basepath, scioperi)

    logging.info('finished')

if __name__ == '__main__':
    try:
        main();
    except Exception, e:
        logging.exception(e)