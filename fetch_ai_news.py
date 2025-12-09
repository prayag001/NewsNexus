#!/usr/bin/env python3
"""
Clean wrapper for fetching AI news with JSON output support.
Suppresses all logging when --json is requested.
"""

import sys
import json
import logging
import argparse

# Check for --json flag before importing main
json_output = '--json' in sys.argv

# Suppress logging if JSON output is requested
if json_output:
    # Set logging to critical level (effectively silent)
    logging.getLogger().setLevel(logging.CRITICAL)
    logging.getLogger('newsnexus').setLevel(logging.CRITICAL)
    
    # Remove all handlers
    for handler in logging.root.handlers[:]:
        logging.root.removeHandler(handler)

# Now import the script that does the work
import get_ai_news_with_fallback

if __name__ == '__main__':
    get_ai_news_with_fallback.main()
