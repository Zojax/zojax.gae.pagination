import math
import logging
import json

from google.appengine.api import memcache
from google.appengine.datastore.datastore_query import Cursor


class PaginatorMixin(object):

    @classmethod
    def _pre_delete_hook(cls, key):
        super(PaginatorMixin, cls)._pre_delete_hook(key)
        memcache.delete(key.kind())

    def _post_put_hook(self, future):
        super(PaginatorMixin, self)._post_put_hook(future)
        memcache.delete(self.key.kind())


class Paginator(object):

    def __init__(self, currpage, q, rows):
        self.currpage, self.q, self.rows = currpage, q, rows


    @classmethod
    def get_query_id(self, query, rows):
        return hash((str(query.filters), str(query.orders), rows))

    def __call__(self):
        #    logging.debug('Paginator started with initial vals: currpage %s, q %s, rows %s ' %(str(currpage), str(q), str(rows)))
        FETCH_LIMIT = 1000
        start = self.rows*(self.currpage - 1)
        query_kind = self.q.kind
        query_key = self.get_query_id(self.q, self.rows)
        query_map_changed = False
        query_map = memcache.get(query_kind)
        if query_map is None:
            query_map ={query_key: {}}
        #print 'memcache cursor:' + str(cursor)
        total_query_objects = query_map.setdefault(query_key, {}).get('total')
        totalpages = query_map.setdefault(query_key, {}).get('pages')
        if total_query_objects is None:
            total_query_objects = self.q.count()
            query_map[query_key]['total'] = total_query_objects
            totalpages = int(math.ceil(total_query_objects/float(self.rows)))
            query_map[query_key]['pages'] = totalpages
            query_map_changed = True

        objects = None
        more = False

        try:
            logging.debug('trying to get objects directly from memcache')
            objects = query_map[query_key]['cursors'][start]['objects']
            more = query_map[query_key]['cursors'][start]['more']
            logging.debug('got some objects!')
        except KeyError:
            query_map[query_key]['cursors'] = {}
            query_map_changed = True

        if objects is None:
            try:
                cursor = query_map[query_key]['cursors'][start]['cursor']
            except KeyError:
                query_map[query_key]['cursors'] = {}
                query_map_changed = True
                cursor = None

            if cursor is not None:
                logging.debug('cursor key found in memcache')
                cursor = Cursor.from_websafe_string(cursor)
            else:
                logging.debug('cursor key not found in memcache. Start looking for the closest cursor')

                cursor, diff = self.get_closest_cursor(start, query_map[query_key]['cursors'])
                #firstly, lets set the cursor on start of page

                while diff > FETCH_LIMIT:
                    logging.debug('diff is %s moving cursor...' %(diff,))
                    objects, cursor, more = self.q.fetch_page(FETCH_LIMIT, start_cursor=cursor, keys_only=True)
                    query_map[query_key]['cursors'][start+diff] = dict(cursor=cursor.to_websafe_string())
                    query_map_changed = True
                    diff -= FETCH_LIMIT

                #ok, lets set cursor more precisely
                if diff:
                    objects, cursor, more = self.q.fetch_page(diff, start_cursor=cursor, keys_only=True)
                    query_map[query_key]['cursors'][start] = dict(cursor=cursor.to_websafe_string())
                    query_map_changed = True
            objects, cursor, more = self.q.fetch_page(self.rows, start_cursor=cursor)
            if objects:
                query_map[query_key]['cursors'][start+len(objects)] = dict(cursor = cursor.to_websafe_string())
                query_map[query_key]['cursors'].setdefault(start, {'objects': objects})['objects'] = objects
                query_map[query_key]['cursors'][start]['more'] = more

        if query_map_changed:
            memcache.set(query_kind, query_map)
        return dict(objects=objects, totalpages=totalpages, totalrecords=total_query_objects, more=more)


    def get_closest_cursor(self, start, cursors):
        keys = filter(lambda x: x< start , cursors.keys())
        if keys:
            lower_cursor = cursors.get(max(*keys))
        else:
            lower_cursor = None
        diff_list = [start]
        if lower_cursor:
            lower_diff = start-lower_cursor.start
            diff_list.append(lower_diff)

        diff = sorted(diff_list)[0]
        if lower_cursor:
            if diff == lower_diff:
                cursor=Cursor.from_websafe_string(lower_cursor.cursor)
        if diff == start:
            cursor = None
        logging.debug('the closest cursor found, diff: %s' %(str(diff)))

        return cursor, diff
