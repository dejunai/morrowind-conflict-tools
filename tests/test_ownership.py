from mwdialog_check import door_owner_verdicts as exported_door_owner_verdicts
from mwdialog_ownership import door_owner_verdicts, item_owner_verdicts


def test_public_door_owner_is_removed_and_api_is_reexported():
    doors = [(('e', 0, 0), 'door ref', 'old_owner', 'Balmora, Tradehouse', '')]
    placements = [(('i', 'ald-ruhn, old owner home'), 'old_owner')]

    result = door_owner_verdicts(doors, placements, {'old_owner': 'commoner'}, {},
                                 {'ald-ruhn, old owner home'})

    assert exported_door_owner_verdicts is door_owner_verdicts
    assert result[0][0] == 'door ref'
    assert result[0][2] == ''


def test_home_objects_are_given_to_its_only_resident():
    cell = ('i', 'balmora, new owner house')
    items = [(cell, 'chest ref', 'old_owner', 'container', '')]
    placements = [
        (('i', 'ald-ruhn, old owner home'), 'old_owner'),
        (cell, 'new_owner'),
    ]

    result = item_owner_verdicts(items, placements,
                                 {'old_owner': 'commoner', 'new_owner': 'commoner'}, {},
                                 {'ald-ruhn, old owner home', cell[1]})

    assert result[0][2] == ['chest ref']
    assert result[0][4] == 'new_owner'
