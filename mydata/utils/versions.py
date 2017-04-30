"""
The MyDataVersions class contains methods to determine whether we are running
the latest official version, an older version, or a newer version.
"""
from datetime import datetime
import json
import os

import dateutil.parser
import pytz
import requests

from ..models import HandleHttpError
from ..settings import SETTINGS

from ..logs import logger

GITHUB_API_BASE_URL = "https://api.github.com/repos/mytardis/mydata"
CACHE_REFRESH_INTERVAL = 300  # seconds


class MyDataVersions(object):
    """
    The MyDataVersions class contains methods to determine whether we are
    running the latest official version, an older version, or a newer
    version.

    The GitHub API will throttle more than 60 connections per hour from the
    same IP address which I can easily reach while testing MyData, so we cache
    results from GitHub API queries.
    """
    def __init__(self):
        self._latestOfficialRelease = None
        self._latestReleases = None

    @property
    def latestOfficialRelease(self):
        """
        Gets the latest official release from the GitHub API.
        """
        if self._latestOfficialRelease:
            return self._latestOfficialRelease
        interval = datetime.utcnow().replace(tzinfo=pytz.utc) - \
            self.latestOfficialReleaseCacheTime
        if interval.total_seconds() > CACHE_REFRESH_INTERVAL:
            url = "%s/releases/latest" % GITHUB_API_BASE_URL
            logger.debug(url)
            response = requests.get(url)
            if response.status_code != 200:
                HandleHttpError(response)
            self._latestOfficialRelease = response.json()
            with open(self.latestOfficialReleaseCachePath, 'w') as cache:
                cache.write(response.text)
        else:
            with open(self.latestOfficialReleaseCachePath, 'r') as cache:
                self._latestOfficialRelease = json.load(cache)
        return self._latestOfficialRelease

    @property
    def latestOfficialReleaseTagName(self):
        """
        Gets the tag for the latest official release.
        """
        return self.latestOfficialRelease['tag_name']

    @property
    def latestOfficialReleaseBody(self):
        """
        Gets the body for the latest official release.
        """
        body = self.latestOfficialRelease['body']
        lines = body.split('\n')
        body = ""
        for line in lines:
            if line.strip() != "```":
                body += "%s\n" % line
        return body

    @property
    def latestOfficialReleaseDateTime(self):
        """
        Returns the date and time (UTC) of the latest official release.
        """
        return dateutil.parser.parse(
            self.latestOfficialRelease['published_at'])

    @property
    def latestOfficialReleaseCachePath(self):
        """
        Response from
        https://api.github.com/repos/mytardis/mydata/releases/latest
        is cached to avoid throttling (only 60 requests are allowed
        per hour from the same IP address).  Throttling is unlikely
        to be an issue in production, but in development, running MyData
        more than 60 times within an hour is common.
        """
        assert SETTINGS.configPath
        return os.path.join(
            os.path.dirname(SETTINGS.configPath),
            "latest-official-release.json")

    @property
    def latestOfficialReleaseCacheTime(self):
        """
        Return time when the latest version cache was last updated.
        """
        try:
            return datetime.utcfromtimestamp(
                os.path.getmtime(self.latestOfficialReleaseCachePath)) \
                .replace(tzinfo=pytz.utc)
        except (OSError, IOError):
            return datetime.utcfromtimestamp(0).replace(tzinfo=pytz.utc)

    @property
    def latestReleases(self):
        """
        Gets the latest 30 releases from the GitHub API.
        30 is the default number of releases per page in the GitHub API.

        They are in reverse chronological order (most recent first).
        """
        if self._latestReleases:
            return self._latestReleases
        interval = datetime.utcnow().replace(tzinfo=pytz.utc) - \
            self.latestReleasesCacheTime
        if interval.total_seconds() > CACHE_REFRESH_INTERVAL:
            url = "%s/releases" % GITHUB_API_BASE_URL
            logger.debug(url)
            response = requests.get(url)
            if response.status_code != 200:
                HandleHttpError(response)
            self._latestReleases = response.json()
            with open(self.latestReleasesCachePath, 'w') as cache:
                cache.write(response.text)
        else:
            with open(self.latestReleasesCachePath, 'r') as cache:
                self._latestReleases = json.load(cache)
        return self._latestReleases

    @property
    def latestReleasesCachePath(self):
        """
        Response from
        https://api.github.com/repos/mytardis/mydata/releases
        is cached to avoid throttling (only 60 requests are allowed
        per hour from the same IP address).  Throttling is unlikely
        to be an issue in production, but in development, running MyData
        more than 60 times within an hour is common.
        """
        assert SETTINGS.configPath
        return os.path.join(
            os.path.dirname(SETTINGS.configPath), "latest-releases.json")

    @property
    def latestReleasesCacheTime(self):
        """
        Return time when the latest releases cache was last updated.
        """
        try:
            return datetime.utcfromtimestamp(
                os.path.getmtime(self.latestReleasesCachePath)) \
                .replace(tzinfo=pytz.utc)
        except (OSError, IOError):
            return datetime.utcfromtimestamp(0).replace(tzinfo=pytz.utc)

    @property
    def latestReleaseTagName(self):
        """
        Gets the tag for the latest release.
        """
        if self.latestReleases:
            tag = self.latestReleases[0]['tag_name']
        else:
            tag = None
        return tag

    @property
    def latestReleaseBody(self):
        """
        Gets the body for the latest release.

        MyData release notes (body) tend to begin with ``` and end with ```
        so that they will be displayed in a fixed width font.
        """
        if self.latestReleases:
            body = self.latestReleases[0]['body']
            lines = body.split('\n')
            body = ""
            for line in lines:
                if line.strip() != "```":
                    body += "%s\n" % line
        else:
            body = None
        return body

    @property
    def latestReleaseDateTime(self):
        """
        Returns the date and time (UTC) of the latest release.
        """
        if self.latestReleases:
            publishedAt = self.latestReleases[0]['published_at']
            latestTime = dateutil.parser.parse(publishedAt)
        else:
            latestTime = None
        return latestTime

    @property
    def latestReleaseIsPreRelease(self):
        """
        Returns True if the latest release is a pre-release.
        """
        if self.latestReleases:
            isPreRelease = self.latestReleases[0]['prerelease']
        else:
            isPreRelease = None
        return isPreRelease


MYDATA_VERSIONS = MyDataVersions()
