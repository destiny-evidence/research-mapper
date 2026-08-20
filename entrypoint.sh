#!/bin/sh
# TEMPORARY. This wraps the research-mapper CLI so ttyd can serve it over the
# web as a proof of concept. Delete this, the ttyd install, and the container
# app's ingress once there's a real HTTP interface.
cat <<'BANNER'

  ############################################################
  #                                                          #
  #   TEMPORARY DEMO -- research-mapper web terminal         #
  #                                                          #
  #   This is a proof of concept, not a product. It runs     #
  #   the CLI as the app's managed identity: your queries    #
  #   hit the DESTINY repository and spend the LLM budget    #
  #   under that identity, with no per-user attribution.     #
  #                                                          #
  #   Do not build anything on top of this URL.              #
  #                                                          #
  ############################################################

BANNER
exec research-mapper
