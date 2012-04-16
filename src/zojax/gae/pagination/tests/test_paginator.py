from unittest import TestCase
import os

try:
    from ndb import model
except ImportError:
    from google.appengine.ext.ndb import model

from google.appengine.ext import testbed
from google.appengine.api import memcache

from zojax.gae.pagination.paginator import Paginator, PaginatorMixin


class TestObject(PaginatorMixin, model.Model):
        email_address = model.StringProperty()
        recipients = model.StringProperty()
        sender = model.StringProperty()
        subject = model.StringProperty()


class PaginateTestCase(TestCase):


    model = TestObject

    def setUp(self):
        # First, create an instance of the Testbed class.
        self.testbed = testbed.Testbed()
        # Then activate the testbed, which prepares the service stubs for use.
        self.testbed.activate()
        # Next, declare which service stubs you want to use.
        self.testbed.init_datastore_v3_stub()
        self.testbed.init_memcache_stub()
        self.testbed.init_mail_stub()
        self.testbed.init_taskqueue_stub(root_path=os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

        #create message
        self.email_address = "larry@example.com"
        self.email_address2 = "bogdan@example.com"
        self.TOTAL_MESSAGES = 2100
        self.ROWS = 2


        for i in range(self.TOTAL_MESSAGES):
            self.model(sender = self.email_address, recipients = self.email_address + ', ' + self.email_address2,
                subject = str(i)
            ).put()
        self.q = self.model.query()

    def test_paginate(self):
        current_page=10
        result = Paginator(current_page, self.q, self.ROWS)()
        self.assertEquals(len(result['objects']), 2)
        self.assertEquals(result['objects'][0].subject, '18')
        self.assertEquals(result['totalpages'], 1050)


    def test_memcache(self):
        current_page=10
        result = Paginator(current_page, self.q, self.ROWS)()
        #check whether query_key saved in memcache
        self.assertTrue(memcache.get(self.q.kind))

#        lets use memcache key to get cursor for the same query
        result = Paginator(current_page, self.q, self.ROWS)()
        self.assertEquals(len(result['objects']), 2)
        self.assertEquals(result['objects'][0].subject, '18')

    def test_far_page(self):
        #use previous StoreCursor to find the closest cursor
        current_page=8
        Paginator(current_page, self.q, self.ROWS)()
        current_page=10
        result = Paginator(current_page, self.q, self.ROWS)()
        self.assertEquals(len(result['objects']), 2)
        self.assertEquals(result['objects'][0].subject, '18')
        self.assertEquals(result['totalrecords'], self.TOTAL_MESSAGES)
        self.assertEquals(result['totalpages'], 1050)

        id = Paginator.get_query_id(self.q, self.ROWS)
        self.assertEquals(len(memcache.get(self.q.kind)[id]['cursors'][18]['objects']),2)

        #test same page again to get results from cache
        result = Paginator(current_page, self.q, self.ROWS)()
        id = Paginator.get_query_id(self.q, self.ROWS)
        self.assertEquals(len(memcache.get(self.q.kind)[id]['cursors'][18]['objects']),2)

    def test_remove_hook(self):
        current_page=8
        Paginator(current_page, self.q, self.ROWS)()
        id = Paginator.get_query_id(self.q, self.ROWS)
        self.assertEquals(len(memcache.get(self.q.kind)[id]['cursors'][14]['objects']),2)
        # delete object
        memcache.get(self.q.kind)[id]['cursors'][14]['objects'][0].key.delete()
        # now memcache should be clear
        self.assertIsNone(memcache.get(self.q.kind))


    def test_empty_query(self):
        result = Paginator(1, self.model.query(self.model.subject=='not existing subject'), self.ROWS)()
        self.assertEquals(len(result['objects']), 0)
        self.assertEquals(result['objects'], [])
        self.assertEquals(result['totalrecords'], 0)
        self.assertEquals(result['totalpages'], 0)
