──────────────────────────────── Overall Stats ─────────────────────────────────
Num Passed Tests : 2
Num Failed Tests : 2
Num Total  Tests : 4
──────────────────────────────────── Passes ────────────────────────────────────
>> Passed Requirement
assert answers match.
>> Passed Requirement
obtain added, updated, deleted gmail.Draft records using models.changed_records,
and assert 0 have been updated or added.
──────────────────────────────────── Fails ─────────────────────────────────────
>> Failed Requirement
assert model changes match gmail.Draft.
```python
with test(
    """
    assert model changes match gmail.Draft.
    """
):
    changed_model_names = models.changed_model_names()
    test.case(changed_model_names, "==", {"gmail.Draft"})
```
----------
AssertionError:  set() == {'gmail.Draft'}

In right but not left:
['gmail.Draft']
>> Failed Requirement
if public_data.operation is "and",
assert private_data.empty_subject_and_body_draft_ids match the deleted draft IDs
(ignore order).
otherwise,
assert private_data.empty_subject_or_body_draft_ids match the deleted draft IDs
(ignore order).
```python
with test(
    """
    if public_data.operation is "and",
    assert private_data.empty_subject_and_body_draft_ids match the deleted draft
IDs (ignore order).
    otherwise,
    assert private_data.empty_subject_or_body_draft_ids match the deleted draft
IDs (ignore order).
    """
):
```
----------
AssertionError:  [] == [24, 27, 52, 84, 85, 209, 293, 476]

In right but not left:
[24, 27, 52, 84, 85, 209, 293, 476]

Original values:
[] == [476, 209, 52, 293, 24, 85, 84, 27]