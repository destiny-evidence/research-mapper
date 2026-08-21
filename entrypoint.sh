#!/bin/sh
cat <<'BANNER'

  ############################################################
  #                                                          #
  #   TEMPORARY DEMO -- research-mapper web terminal         #
  #                                                          #
  #   Replace me with an API, database and UI!               #
  #                                                          #
  ############################################################

BANNER
alembic upgrade head

exec research-mapper
