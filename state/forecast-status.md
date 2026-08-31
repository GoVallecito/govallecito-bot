# Forecast run — crashed

When: 2026-08-30T22:37:44-06:00 (Mountain)

## Detail

```
Traceback (most recent call last):
  File "/home/runner/work/govallecito-bot/govallecito-bot/scripts/wx/run_forecast.py", line 276, in <module>
    _code = main()
            ^^^^^^
  File "/home/runner/work/govallecito-bot/govallecito-bot/scripts/wx/run_forecast.py", line 271, in main
    return run(slot=determine_slot(forced=args.slot), site_dir=args.site_dir)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/govallecito-bot/govallecito-bot/scripts/wx/run_forecast.py", line 131, in run
    text = CO.compose(bundle, llm, post_type=slot)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/govallecito-bot/govallecito-bot/scripts/wx/compose.py", line 247, in compose
    return llm(build_messages(bundle, post_type=post_type, **kw))
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/home/runner/work/govallecito-bot/govallecito-bot/scripts/wx/run_forecast.py", line 73, in call
    with urllib.request.urlopen(req, timeout=120) as resp:
         ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/urllib/request.py", line 216, in urlopen
    return opener.open(url, data, timeout)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/urllib/request.py", line 525, in open
    response = meth(req, response)
               ^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/urllib/request.py", line 634, in http_response
    response = self.parent.error(
               ^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/urllib/request.py", line 563, in error
    return self._call_chain(*args)
           ^^^^^^^^^^^^^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/urllib/request.py", line 496, in _call_chain
    result = func(*args)
             ^^^^^^^^^^^
  File "/opt/hostedtoolcache/Python/3.11.16/x64/lib/python3.11/urllib/request.py", line 643, in http_error_default
    raise HTTPError(req.full_url, code, msg, hdrs, fp)
urllib.error.HTTPError: HTTP Error 401: Unauthorized
```

