"""Machine operation fields shared by the facade, schema and guide checks."""
FIELDS = {
 'capabilities': (set(), set()), 'inspect': (set(), set()), 'validate': (set(), set()),
 'tasks.query': (set(), {'op','id','text','name','detail','since'}),
 'tasks.command': (set(), None),
 'actions.plan': (set(), set()),
 'actions.claim': ({'action_id','expected_revision'}, {'action_id','expected_revision'}),
 'runs.query': (set(), {'run_id'}),
 'runs.cancel': ({'run_id','expected_revision','reason'}, {'run_id','expected_revision','reason'}),
 'runs.event': ({'run_id','expected_revision','kind'}, {'run_id','expected_revision','kind','receipt','pid','model','exit_code','usage','evidence','summary','reason','commands'}),
 'runtime.configure': ({'mode','expected_generation'}, {'mode','expected_generation'}),
 'scripts.inspect': (set(), set()), 'scripts.request': ({'id'}, {'id','args'}),
 'expert.prepare': ({'id','version','profession','url','commit'}, {'id','version','profession','url','commit','subdir'}),
 'expert.adapt': ({'id','version','methods','review'}, {'id','version','methods','review','unresolved'}),
 'expert.validate': ({'id','version','evidence'}, {'id','version','evidence'}),
 'expert.enable': ({'id','version'}, {'id','version'}),
 'expert.disable': ({'id','version','reason'}, {'id','version','reason'}),
}


def validate(operation, params):
    required, fields = FIELDS[operation]
    if not required <= params.keys() or fields is not None and not params.keys() <= fields:
        raise ValueError('operation params have missing or unknown fields')
    for field in ('expected_revision','expected_generation'):
        if field in params and (type(params[field]) is not int or params[field] < 0):
            raise ValueError(field+' must be a nonnegative integer')
