import cjson
import logging
import glob
import warnings
import ntpath
import argparse
import os
warnings.filterwarnings('ignore', 'unknown table')

logging.basicConfig(filename='example.log')
logging.getLogger('sqlalchemy.engine').setLevel(logging.DEBUG)

from sqlalchemy import Table, Column, create_engine, MetaData, VARCHAR, CHAR, TEXT, BIGINT, INTEGER, select
from progressbar import SimpleProgress, ProgressBar


class Clickstream(object):
    # __init__  is triggered when an instance of the class is instanciated.
    #
    # course    is the he name of the course followed by the iteration, e.g edivet002.
    #           this is generated by taking the file name of the json_file up until the first _.
    #           with the - removed. For example edivet-002_clickstream_export.json becomes edivet002.
    #
    # json_file

    def __init__(self, course, json_file):
        # Dictionary containing the database connection metadata
        # hostname      The IP or hostname of the server the database is running on. This will be
        #               127.0.0.1 if the server is being run locally.
        # username      The username of the user that has access privilages to the database.
        #
        # password      The password of the user that has access privilages to the database.

        course = ntpath.basename(course)

        self.user = {
            'hostname': "127.0.0.1",
            'username': "root",
            'password': "root",
        }

        # Dictionary containing the database connection metadata
        # course        The name of the course that is currently being processed. This is established
        #               by taking the file name until the first _ e.g edivet002_.... becomes edivet002.
        #
        # database      The name of the database that will hold the clickstream data, this is the
        #               name of the course prepended with "cls_", eg "cls_edivet002" for the edivet002 course.
        #
        # json          The path to the JSON file containing the clickstream data

        self.info = {
            'course': course,
            'database': "cls_" + course.replace("-", ""),
            'json': json_file,
        }

        drop = 'echo "DROP DATABASE IF EXISTS" '
        create = 'echo "CREATE DATABASE " '
        mysql_pipe = ' | mysql -h '

        # If the database we are going to use exists, DROP it to avoid any problems
        os.system(drop + self.info['database'] + mysql_pipe + self.user['hostname'])

        # Then create it again.
        os.system(create + self.info['database'] + mysql_pipe + self.user['hostname'])

        # Create the database connection using SQLAlchemy, bind the metadata to a variable
        self.engine = create_engine(
            'mysql://' +
            self.user['username'] + ':' +
            self.user['password'] + '@' +
            self.user['hostname'] + '/' +
            self.info['database'] + '?charset=utf8')
        self.metadata = MetaData(self.engine)

        self.conn = self.engine.connect()
        self.t = self.conn.begin()

    def disconnect(self):
        self.conn.close()

    def load(self):
        self.conn.execute("DROP TABLE IF EXISTS " + self.info['database'] + "_uniques;")
        self.conn.execute("DROP TABLE IF EXISTS " + self.info['database'] + "_clicks;")
        self.clickstream = Table(self.info['database'], self.metadata,
                                 Column('username', VARCHAR(120)),
                                 Column('13', CHAR(1)),
                                 Column('12', VARCHAR(255)),
                                 Column('from', VARCHAR(4095)),
                                 Column('language', VARCHAR(2047)),
                                 Column('session', VARCHAR(255)),
                                 Column('timestamp', BIGINT),
                                 Column('30', VARCHAR(255)),
                                 Column('value', VARCHAR(4095)),
                                 Column('user_ip', VARCHAR(255)),
                                 Column('client', VARCHAR(255)),
                                 Column('user_agent', VARCHAR(1000)),
                                 Column('key', TEXT),
                                 Column('14', VARCHAR(4095)),
                                 Column('page_url', VARCHAR(2045)),
                                 mysql_engine='InnoDB',
                                 mysql_charset='utf8')
        self.clickstream.create()

        inserts = []
        num_lines = sum(1 for line in open(self.info['json']))
        print "Loading: " + self.info['course']
        with open(self.info['json']) as f:
            pbar = ProgressBar(widgets=['Event ', SimpleProgress()], maxval=num_lines).start()
            progress = 0
            self.max = {
                'username': 0,
                '13': 0,
                '12': 0,
                'from': 0,
                'language': 0,
                'session': 0,
                'timestamp': 0,
                '30': 0,
                'value': 0,
                'user_ip': 0,
                'client': 0,
                'user_agent': 0,
                'key': 0,
                '14': 0,
                'page_url': 0,
            }

            for line in f:
                data = cjson.decode(line.replace('\r\n', ''))

                if "user_agent" not in data.keys():
                    data['user_agent'] = 'Unknown'

                if "30" not in data.keys():
                    data['30'] = 'Unknown'
                else:
                    data['30'] = data['30']

                if "14" not in data.keys():
                    data['14'] = 'Unknown'
                else:
                    data['14'] = data['14'][0]

                if "from" not in data.keys():
                    data['from'] = 'Unknown'

                if "language" not in data.keys():
                    data['language'] = 'Unknown'

                for key in data.keys():
                    try:
                        if len(data[key]) > self.max[key]:
                            self.max[key] = len(data[key])
                    except TypeError:
                        if len(str(data[key])) > self.max[key]:
                            self.max[key] = len(str(data[key]))

                inserts.append(data)
                pbar.update(progress)
                progress = progress + 1
                if progress % 1000 == 0:
                    try:
                        self.conn.execute(self.clickstream.insert(), inserts)
                        self.t.commit()
                    except:
                        self.t.rollback()
                    inserts = []

            pbar.finish()

            try:
                self.conn.execute(self.clickstream.insert(), inserts)
                self.conn.execute("COMMIT();")
                self.t.commit()
            except:
                self.t.rollback()

            for key in self.max.keys():
                print "Biggest " + key + ": " + str(self.max[key])

    def users_per_day(self):
        print "Processing: " + self.info['course']
        users_per_day = Table(self.info['database'] + "_uniques", self.metadata,
                              Column('date_visited', VARCHAR(10)),
                              Column('unique_users', INTEGER),
                              mysql_engine='InnoDB',
                              mysql_charset='utf8mb4'
                              )
        users_per_day.create()

        sql = """INSERT INTO {0}
        (date_visited, unique_users)
        SELECT date_visited, count(username) as unique_users FROM
        (
            SELECT DISTINCT from_unixtime(timestamp / 1000, '%%Y-%%m-%%d') as date_visited, username FROM {1}
        ) as a
        GROUP BY date_visited
        ORDER BY date_visited ASC;""".format(self.info['database'] + "_uniques", self.info['database'])

        try:
            self.conn.execute(sql)
            self.t.commit()
        except:
            self.t.rollback()

    def clicks_per_user_per_day(self):
        users_per_day = Table(self.info['database'] + "_clicks", self.metadata,
                              Column('username', VARCHAR(50)),
                              Column('date_visited', VARCHAR(10)),
                              Column('clicks', INTEGER),
                              mysql_engine='InnoDB',
                              mysql_charset='utf8mb4'
                              )
        users_per_day.create()

        s = select([self.clickstream])
        users = self.conn.execute(s)
        for user in users:
            sql = """INSERT INTO {0}
                (username, date_visited, clicks)
                SELECT username, from_unixtime(timestamp / 1000, '%%Y-%%m-%%d') as date_visited, count(username) as clicks FROM {1}
                WHERE username = "{2}"
                GROUP BY date_visited;""".format(self.info['database'] + "_clicks", self.info['database'], user[0])

            try:
                self.conn.execute(sql)
                self.t.commit()
            except:
                self.t.rollback()

parser = argparse.ArgumentParser(description='Process some files.')
parser.add_argument("-d", "--directory", help="Process an entire directory")
parser.add_argument("-f", "--file", help="Process a file")

args = parser.parse_args()
if args.directory:
    for file_name in glob.glob(args.directory + '*.*'):
        if os.path.isdir(args.directory):
            a = Clickstream(file_name.split("_")[0].replace("-", ""), file_name)
            a.load()
            a.users_per_day()
            a.clicks_per_user_per_day()
            a.disconnect()
        else:
            print "You must specify a directory"
elif args.file:
        if os.path.isfile(args.file):
            a = Clickstream(str(args.file).split("_")[0].replace("-", ""), str(args.file))
            a.load()
            a.users_per_day()
            a.clicks_per_user_per_day()
            a.disconnect()
        else:
            print "You must specify a file"
