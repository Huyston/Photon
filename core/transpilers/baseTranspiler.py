from interpreter import Interpreter
from copy import deepcopy
import os

class BaseTranspiler():
    def __init__(self, filename, target='web', module=False, standardLibs=''):
        self.debug = False # make this a global variable instead, inseide the debug module
        self.standardLibs = standardLibs
        self.target = target
        self.lang = 'photon'
        self.libExtension = 'photonExt'
        self.filename = filename.split('/')[-1].replace('.w','.photon')
        self.module = module

        self.operators = ['**','*','%','/','-','+','==','!=','>','<','>=','<=','is','in','andnot','and','or','&', '<<', '>>'] # in order 
        self.instructions = {
            'printFunc': self.printFunc,
            'inputFunc': self.processInput,
            'expr': self.processExpression,
            'assign': self.processAssign,
            'augAssign': self.processAugAssign,
            'if': self.processIf,
            'while': self.processWhile,
            'for': self.processFor,
            'func': self.processFunc,
            'class': self.processClass,
            'return': self.processReturn,
            'breakStatement': self.processBreak,
            'comment': self.processComment,
            'import': self.processImport,
            '+': self.add,
            '-': self.sub,
            '*': self.mul,
            '/': self.div,
            '%': self.mod,
            '**': self.exp,
            '<': self.lessThan,
            '>': self.greaterThan,
            '==': self.equals,
            '>=': self.greaterEqual,
            '<=': self.lessEqual,
            '!=': self.notEqual,
            'and': self.andOperator,
            'or': self.orOperator,
        }
        self.terminator = ';'
        self.currentScope = {}
        # Old scope is a list because of nested scopes.
        # E.g. methods of a class have the classScope and the method scope
        self.oldScope = []
        self.classes = {}
        self.inFunc = None
        self.inClass = None
        self.methodsInsideClass = True
        self.insertMode = True
        self.source = []
        self.outOfMain = []
        self.nativeTypes = {
            'int':'int',
            'float':'float',
            'void':'void',
            'array':'array',
            'unknown':'auto',
        }

    def insertCode(self, line, index=None):
        if self.insertMode:
            if self.inFunc or self.inClass:
                if not index is None:
                    self.outOfMain.insert(index, line)
                else:
                    self.outOfMain.append(line)
            else:
                if not index is None:
                    self.source.insert(index, line)
                else:
                    self.source.append(line)

    def process(self, token):
        self.instructions[token['opcode']](token)

    def nativeType(self, varType):
        if varType in self.nativeTypes:
            return self.nativeTypes[varType]
        elif self.typeKnown(varType):
            return varType
        else:
            raise NotImplemented

    def getType(self, name):
        try:
            return self.currentScope[name]['type']
        except KeyError:
            pass
        try:
            if '.' in name:
                float(name)
                return 'float'
            else:
                int(name)
                return 'int'
        except ValueError:
            pass
        return 'unknown'


    def inferType(self, expr):
        if self.typeKnown(expr['type']):
            return expr['type']
        else:
            print('Infering type')
            input(expr)
            return 'unknown'
            raise NotImplemented

    def typeKnown(self, varType):
        if varType in {'unknown', self.nativeType('unknown')}:
            return False
        return True

    def processInput(self, token):
        if 'expr' in token:
            expr = self.processExpr(token['expr'])
        else:
            expr = {'type':'null', 'value':''}
        return {'token':'inputFunc', 'type':'str', 'value':self.formatInput(expr)}

    def processVarInit(self, token):
        name = token['args'][0]['name']
        varType = token['args'][0]['type']
        if self.typeKnown(varType):
            self.currentScope[name] = {'type':varType}
        self.insertCode(self.formatVarInit(name, varType))

    def processVar(self, token):
        name = token['name']
        if self.typeKnown(token['type']):
            # Type was explicit
            varType = token['type']
        elif name in self.currentScope:
            # Already processed
            varType = self.currentScope[name]['type']
            if varType == 'array':
                token['elementType'] = self.currentScope[name]['elementType']
                token['size'] = self.currentScope[name]['size']
        elif name == self.inFunc and self.returnType:
            for rt in self.returnType:
                if self.typeKnown(rt):
                    varType = rt
                    # If return is an array, get other info
                    if varType == 'array':
                        token['elementType'] = self.currentScope[name]['elementType']
                        token['size'] = self.currentScope[name]['size']
        else:
            varType = 'unknown'
        if 'modifier' in token:
            #TODO: This should go after indexAccess
            token['name'] = token['modifier'].replace('not',self.notOperator) + token['name']
        if varType == 'array':
            if 'indexAccess' in token:
                # Accessing an element of the array
                token['type'] = varType
                v = self.processIndexAccess(token)
                return {'value':v['value'],
                    'indexAccess':token['indexAccess'], 'type':v['type']}
            return {'value':token['name'], 'type':varType,
                'elementType':token['elementType'], 'size':token['size']}
        return {'value':token['name'], 'type':varType}

    def processIndexAccess(self, token):
        if token['type'] == 'array':
            varType = token['elementType']
            return {'value':self.formatIndexAccess(token),
                'type':varType}
        else:
            raise SyntaxError(f'IndexAccess with type {token["type"]} not implemented yet')

    def processFormatStr(self, token):
        expressions = [self.processExpr(expr) for expr in token['expressions']]
        string, expressions = self.formatStr(token['value'], expressions)
        if expressions:
            # It's a format string
            token['values'] = expressions
            token['format'] = string
        else:
            # Normal string
            token['value'] = string
        return token

    def processArray(self, token):
        # InferType
        types = set()
        elements = []
        for tok in token['elements']:
            element = self.getValAndType(tok)
            types.add(element['type'])
            elements.append(element)
        if self.typeKnown(token['elementType']):
            # Type was explicit
            varType = token['elementType']
        else:
            # Infer type
            if len(types) == 0:
                varType = 'unknown'
            elif len(types) == 1:
                varType = types.pop()
            elif len(types) == 2:
                t1 = types.pop()
                t2 = types.pop()
                if t1 in {'int','float'} and t2 in {'int','float'}:
                    varType = 'float'
                else:
                    raise SyntaxError(f'Type inference in array with types {t1} and {t2} not implemented yet.')
            else:
                raise SyntaxError(f'Type inference in array with types {types} not implemented yet.')
        return {'value':self.formatArray(elements, varType, token['size']), 'type':'array',
        'elements':elements, 'elementType':varType, 'size':'unknown'}

    def getValAndType(self, token):
        if 'value' in token and 'type' in token and (self.typeKnown(token['type']) or not self.insertMode):
            if token['type'] == 'str':
                token = self.processFormatStr(token)
            elif token['type'] == 'bool':
                if token['value'].lower() == 'false':
                    token['value'] = self.false
                elif token['value'].lower() == 'true':
                    token['value'] = self.true
            if 'modifier' in token:
                token['value'] = token['modifier'] + token['value']
            return token
        elif token['token'] == 'expr':
            return self.processExpr(token)
        elif token['token'] == 'call':
            return self.processCall(token)
        elif token['token'] == 'group':
            return self.processGroup(token)
        elif token['token'] == 'var':
            return self.processVar(token)
        elif token['token'] == 'dotAccess':
            return self.processDotAccess(token)
        elif token['token'] == 'inputFunc':
            return self.processInput(token)
        elif token['token'] == 'array':
            return self.processArray(token)
        else:
            raise ValueError(f'ValAndType with token {token} not implemented')

    def processExpression(self, token):
        ''' Process the expr token as a standalone code '''
        expr = self.processExpr(token)
        self.insertCode(expr['value']+self.terminator)

    def processExpr(self, token):
        ''' Process expr tokens as values, returning its type and value '''
        args = token['args']
        ops = token['ops']
        if not ops:
            tok = args[0]
            return self.getValAndType(tok)
        elif len(args) == 1 and len(ops) == 1:
            # modifier operator
            if self.typeKnown(token['type']):
                return {'value':ops[0]+token['args'][0]['value'],'type':token['type']}
            else:
                raise NotImplemented
        else:
            for op in self.operators:
                while op in ops:
                    index = ops.index(op)
                    arg1 = args[index]
                    arg2 = args[index+1]
                    arg1 = self.getValAndType(arg1)
                    arg2 = self.getValAndType(arg2)
                    result = self.instructions[op](arg1, arg2)
                    args[index] = result
                    del ops[index]
                    del args[index+1]
            return args[0]

        return token['args'][0]

    def processClassAttribute(self, token):
        #TODO: Handle dict types
        variable = self.processVar(token['target'])
        expr = token['expr']
        if self.typeKnown(variable['type']) and expr['args'][0]['type'] == 'array':
            # The type declaration is for the elementType
            variable['elementType'] = variable['type']
            expr['args'][0]['elementType'] = variable['type']
            variable['type'] = 'array'
            if not 'size' in variable:
                variable['size'] = expr['args'][0]['size']
        expr = self.processExpr(expr)
        if not self.typeKnown(variable['type']):
            variable['type'] = expr['type']
        self.classes[self.inClass]['scope'][variable['value']] = {'type': variable['type']}
        self.classes[self.inClass]['attributes'].append(
            {'name':variable['value'],
            'type':variable['type'],
            'value':expr}
        )
        if variable['type'] == 'array':
            if not 'elementType' in variable:
                variable['elementType'] = expr['elementType']
                variable['size'] = expr['size']
            self.classes[self.inClass]['scope'][variable['value']]['elementType'] = variable['elementType']
            self.classes[self.inClass]['scope'][variable['value']]['size'] = variable['size']
            self.classes[self.inClass]['attributes'][-1]['elementType'] = variable['elementType']
            self.classes[self.inClass]['attributes'][-1]['size'] = variable['size']
        self.insertCode(self.formatClassAttribute(variable, expr))

    def processAssign(self, token):
        target = token['target']
        expr = token['expr']
        if target['token'] in {'var', 'dotAccess'}:
            #variable = self.processVar(target)
            variable = self.getValAndType(target)
            if variable['type'] == 'array':
                if not self.typeKnown(expr['args'][0]['elementType']):
                    # Add array info into expression
                    expr['args'][0]['elementType'] = variable['elementType']
                    expr['args'][0]['size'] = variable['size']
            elif self.typeKnown(variable['type']) and expr['args'][0]['type'] == 'array':
                # The type declaration is for the elementType
                expr['args'][0]['elementType'] = variable['type']
        else:
            raise SyntaxError(f'Assign with variable {target} no supported yet.')
        expr = self.processExpr(expr)
        inMemory = False
        if variable['value'] in self.currentScope or target['token'] == 'dotAccess':
            inMemory = True
        elif self.typeKnown(variable['type']):
            self.currentScope[variable['value']] = {'type':variable['type']}
            if variable['type'] == 'array':
                self.currentScope[variable['value']]['elementType'] = variable['elementType']
                self.currentScope[variable['value']]['size'] = variable['size']
                #if not self.typeKnown(expr['elementType']):
                #    expr['elementType'] = variable['elementType']
                #    expr['len'] = variable['len']
            elif expr['type'] == 'array':
                self.currentScope[variable['value']]['elementType'] = expr['elementType']
                self.currentScope[variable['value']]['size'] = expr['size']
                # We have to change the type to array because the type declaration was intended
                # for the elementType
                self.currentScope[variable['value']]['type'] = 'array'

        else:
            varType = self.inferType(expr)
            if self.typeKnown(varType):
                self.currentScope[variable['value']] = {'type':varType}
                if varType == 'array':
                    if self.typeKnown(expr['elementType']):
                        self.currentScope[variable['value']]['elementType'] = expr['elementType']
                    elif self.typeKnown(variable['type']):
                        self.currentScope[variable['value']]['elementType'] = variable['type']
                    else:
                        raise SyntaxError(f'Array with unknown type not implemented yet.')
                    self.currentScope[variable['value']]['size'] = expr['size']
                target['type'] = varType
        #if 'indexAccess' in target:
        if 'indexAccess' in variable:
            self.insertCode(self.formatIndexAssign(target, expr, inMemory=inMemory))
        else:
            self.insertCode(self.formatAssign(target, expr, inMemory=inMemory))

    def processAugAssign(self, token):
        op = token['operator']
        expr = self.processExpr(token['expr'])
        if token['target']['token'] in {'var','dotAccess'}:
            variable = self.getValAndType(token['target'])
            if op == '+':
                if variable['type'] == 'array':
                    self.insertCode(self.formatArrayAppend(variable, expr))
                elif 'indexAccess' in variable:
                    indexVal = variable['indexAccess']['args'][0]
                    index = indexVal['value'] if 'value' in indexVal else indexVal['name']
                    self.insertCode(self.formatArrayIncrement(token['target'], index, expr))
                elif variable['type'] in {'int', 'float'}:
                    self.insertCode(self.formatIncrement(variable, expr))
                else:
                    raise SyntaxError(f'AugAssign with type {variable["type"]} not implemented yet.')
        else:
            raise SyntaxError(f'AugAssign with variable {token["target"]} not supported yet.')

    def formatIndexAccess(self, token):
        if token['type'] == 'array':
            indexAccess = self.processExpr(token['indexAccess'])['value']
            name = token['name']
            return f'{name}[{indexAccess}]'
        else:
            raise SyntaxError(f'IndexAccess with type {token["type"]} not implemented yet')

    def processIf(self, token):
        expr = self.processExpr(token['expr'])
        self.insertCode(self.formatIf(expr))
        for c in token['block']:
            self.process(c)
        if 'elifs' in token:
            for elifStatement in token['elifs']:
                expr = self.processExpr(elifStatement['expr'])
                self.insertCode(self.formatElif(expr))
                for c in elifStatement['elifBlock']:
                    self.process(c)
        if 'else' in token:
            self.insertCode(self.formatElse())
            for c in token['else']:
                self.process(c)
        self.insertCode(self.formatEndIf())

    def processWhile(self, token):
        expr = self.processExpr(token['expr'])
        self.insertCode(self.formatWhile(expr))
        for c in token['block']:
            self.process(c)
        self.insertCode(self.formatEndWhile())

    def processRange(self, token):
        rangeType = 'unknown'
        fromVal = self.processExpr(token['from'])
        if 'step' in token:
            step = self.processExpr(token['from'])
        else:
            step = {'type':'int', 'value':'1'}
        toVal = self.processExpr(token['to'])
        types = {fromVal['type'], step['type'], toVal['type']}
        if len(types) == 1:
            rangeType = types.pop()
        elif len(types) == 2 and 'float' in types and 'int' in types:
            rangeType = 'float'
        return {'type':rangeType, 'from':fromVal, 'step':step, 'to':toVal}

    def processFor(self, token):
        if token['iterable']['token'] == 'expr':
            iterable = self.processExpr(token['iterable'])
        else:
            iterable = self.processRange(token['iterable'])
        variables = [ self.processVar(v) for v in token['vars'] ]
        self.insertCode(self.formatFor(variables, iterable))
        #TODO: Handle dict iteration and multivar for loop
        if iterable['type'] == 'array':
            self.currentScope[variables[-1]['value']] = {'type':iterable['elementType']}
        else:
            self.currentScope[variables[-1]['value']] = {'type':iterable['type']}
        for c in token['block']:
            self.process(c)
        self.insertCode(self.formatEndFor())

    def processArgs(self, tokens, inferType=False):
        args = []
        for tok in tokens:
            arg = self.getValAndType(tok)
            if inferType:
                args.append( {'type':arg['type'], 'value':arg['value']} )
            else:
                # ignore value type because of the scope
                # Function arguments need explicit type
                args.append( {'type':tok['type'], 'value':arg['value']} )
        return args

    def processKwargs(self, tokens):
        kwargs = []
        for tok in tokens:
            kw = self.getValAndType(tok['expr'])
            name = tok['target']['name']
            # ignore value type because of the scope
            # Function keyword arguments need explicit type or inferred from expr
            if self.typeKnown(tok['target']['type']):
                varType = tok['target']['type']
            else:
                varType = kw['type']
            kwargs.append( {'type':varType, 'name':name, 'value':kw['value']} )
        return kwargs

    def processCall(self, token, className=None):
        name = self.getValAndType(token['name'])
        args = self.processArgs(token['args'], inferType=True)
        # Put kwargs in the right order
        if not className is None:
            kws = self.classes[className]['scope'][name['value']]['kwargs']
        elif name['value'] in self.currentScope:
            kws = self.currentScope[name['value']]['kwargs']
        else:
            # Call signature not defined, use the order it was passed
            kws = self.processKwargs(token['kwargs'])
        kwargs = []
        # If the kwarg was passed, use it. Otherwise use the default value
        for kw in kws:
            for a in self.processKwargs(token['kwargs']):
                if kw['name'] == a['name']:
                    kwargs.append(a)
                    break
            else:
                kwargs.append(kw)
        if name['value'] in self.classes:
            callType = name['value']
        else:
            callType = name['type']
        val = self.formatCall(name['value'], name['type'], args, kwargs)
        if 'modifier' in token:
            val = token['modifier'].replace('not',self.notOperator) + val
        return {'value':val, 'type':callType}

    def processDotAccess(self, token):
        tokens = token['dotAccess']
        varType = self.processVar(tokens[0])['type']
        currentType = varType
        tokens[0]['type'] = varType
        for n, v in enumerate(tokens[1:], 1):
            if varType in self.classes:
                if v['token'] == 'call':
                    name = v['name']['name']
                else:
                    name = v['name']
                if name in self.classes[varType]['scope']:
                    currentType = self.classes[varType]['scope'][name]['type']
                    if currentType == 'array':
                        varType = self.classes[varType]['scope'][name]['elementType']
                        tokens[n]['type'] = currentType
                        tokens[n]['elementType'] = varType
                    else:
                        varType = currentType
                        tokens[n]['type'] = varType
            elif currentType == 'array' and v['name'] == 'len':
                tokens[n]['type'] = 'int'
                currentType = 'int'
                varType = 'int'
        value = self.formatDotAccess(tokens)
        
        # pass other arguments to be compatible with processVar method
        if currentType == 'array':
            if 'indexAccess' in tokens[-1]:
                # Accessing an element of the array
                #tokens[-1]['type'] = varType
                return {'value': value, #tokens[-1]['name'],
                    'indexAccess':tokens[-1]['indexAccess'],
                    'type':varType}
            return {'value':value, 'type':currentType,
                'elementType':tokens[-1]['elementType'], 'size':'unknown'}

        return {'value':value, 'type':varType}

    def startScope(self):
        self.oldScope.append(deepcopy(self.currentScope))
        # refresh returnType
        self.returnType = set()

    def endScope(self):
        scope = deepcopy(self.currentScope)
        self.currentScope = self.oldScope.pop()
        return scope

    def processClass(self, token):
        name = token['name']
        self.inClass = name
        self.classes[name] = {'scope':{}, 'attributes':[],'methods':{}}
        self.startScope()
        index = len(self.outOfMain)
        for c in token['block']:
            if c['token'] == 'assign':
                self.processClassAttribute(c)
            elif c['token'] == 'func':
                self.processClassMethods(c)
            elif c['token'] == 'comment':
                self.processComment(c)
            else:
                raise SyntaxError(f'Cannot use {c["token"]} inside a class')
        classScope = self.endScope()
        # Include methods, args/kwargs
        args = self.processArgs(token['args'])
        self.insertCode(self.formatClass(name, args), index)
        if not self.methodsInsideClass:
            # Close class definition before writing methods
            self.insertCode(self.formatEndClass())
        # Write methods code
        for methodName, info in self.classes[self.inClass]['methods'].items():
            self.insertCode('')
            self.classes[name]['scope'][methodName] = info['scope'][methodName]
            for c in info['code']:
                self.insertCode(c)
        if self.methodsInsideClass:
            # Close class definition after writing methods
            self.insertCode(self.formatEndClass())
        self.inClass = None

    def processClassMethods(self, token):
        selfArg = {
            'token': 'expr',
            'type': self.inClass,
            'args': [{'token': 'var', 'name': 'self', 'type': self.inClass}], 'ops': []}
        token['args'] = [selfArg] + token['args']
        index = len(self.outOfMain)
        self.processFunc(token)
        methodCode = self.outOfMain[index:]
        del self.outOfMain[index:]
        self.classes[self.inClass]['methods'][token['name']] = deepcopy(self.currentScope[token['name']])
        self.classes[self.inClass]['methods'][token['name']]['code'] = methodCode
        del self.currentScope[token['name']]

    def processFunc(self, token):
        #TODO: add support for kwargs
        args = self.processArgs(token['args'])
        kwargs = self.processKwargs(token['kwargs'])
        name = token['name']
        returnType = token['type']
        self.returnType = returnType
        self.inFunc = name
        # infer return type if not known
        if not self.typeKnown(returnType):
            # Pre process code and get returnType
            # change mode to not insert code on processing
            self.insertMode = False
            self.startScope()
            # put args in scope
            for arg in args:
                argType = arg['type']
                argVal = arg['value']
                self.currentScope[argVal] = {'type':argType}
            # put kwargs in scope
            for kw in kwargs:
                kwType = kw['type']
                kwVal = kw['name']
                self.currentScope[kwVal] = {'type':kwType}
            # get a deepcopy or it will corrupt the block
            block = deepcopy(token['block'])
            for c in block:
                self.process(c)
            for rt in self.returnType:
                if self.typeKnown(rt):
                    returnType = rt
                    break
            else:
                returnType = 'void'
            self.endScope()
            # return to normal mode
            self.insertMode = True
            # End pre processing
        self.startScope()
        self.currentScope[name] = {'type':returnType, 'token':'func', 'args':args, 'kwargs':kwargs}
        index = len(self.outOfMain)
        # put args in scope
        for arg in args:
            argType = arg['type']
            argVal = arg['value']
            self.currentScope[argVal] = {'type':argType}
        # put kwargs in scope
        for kw in kwargs:
            kwType = kw['type']
            kwVal = kw['name']
            self.currentScope[kwVal] = {'type':kwType}
        for c in token['block']:
            self.process(c)
        self.insertCode(self.formatFunc(name, returnType, args, kwargs),index)
        self.insertCode(self.formatEndFunc())
        self.inFunc = None
        funcScope = self.endScope()
        self.currentScope[name] = {'scope':funcScope, 'type':returnType, 'token':'func', 'args':args, 'kwargs':kwargs}

    def processReturn(self, token):
        if 'expr' in token:
            expr = self.processExpr(token['expr'])
            self.returnType.add(expr['type'])
        else:
            expr = None
            self.returnType.add('void')
        self.insertCode(self.formatReturn(expr))

    def processBreak(self, token):
        self.insertCode('break'+self.terminator)

    def processComment(self, token):
        # Do nothing for now
        pass

    def processImport(self, token):
        folder = None
        if token['expr']['args'][0]['token'] == 'var':
            name = token['expr']['args'][0]['name']
            if f"{name}.w" in os.listdir(folder):
                # Local module import
                interpreter = Interpreter(
                        filename=f'{name}.w',
                        lang=self.lang,
                        target=self.target,
                        module=True,
                        standardLibs=self.standardLibs,
                        transpileOnly=True,
                        debug=self.debug)
                interpreter.run()
                self.classes.update(interpreter.engine.classes)
                self.currentScope.update(interpreter.engine.currentScope)
                self.imports = self.imports.union(interpreter.engine.imports)
                self.links = self.links.union(interpreter.engine.links)
                self.outOfMain += interpreter.engine.outOfMain
                self.source += interpreter.engine.source
            elif f"{name}.w" in os.listdir(self.standardLibs):
                # Photon module import
                raise SyntaxError('Photon module import not implemented yet.')
            elif f"{name}.{self.libExtension}" in os.listdir(self.standardLibs + f'/native/{self.lang}/'):
                # Native Photon lib module import
                raise SyntaxError('Native Photon module import not implemented yet.')
            elif f"{name}.{self.libExtension}" in os.listdir():
                # Native Photon local module import
                raise SyntaxError('Native Photon local module import not implemented yet.')
            else:
                # System library import
                self.insertCode(self.formatSystemLibImport(token['expr']))

    def printFunc(self, token):
        if 'expr' in token:
            value = self.processExpr(token['expr'])
        else:
            value = {'value':'','type':'null'}
        self.insertCode(self.formatPrint(value))

    def add(self, arg1, arg2):
        t1 = arg1['type']
        t2 = arg2['type']
        if t1 == 'int' and t2 == 'int':
            varType = 'int'
        elif t1 in {'float','int'} and t2 in {'float','int'}:
            varType = 'float'
        else:
            varType = 'unknown'
        return {'value':f'{arg1["value"]} + {arg2["value"]}', 'type':varType}

    def sub(self, arg1, arg2):
        t1 = arg1['type']
        t2 = arg2['type']
        if t1 == 'int' and t2 == 'int':
            varType = 'int'
        elif t1 in {'float','int'} and t2 in {'float','int'}:
            varType = 'float'
        else:
            varType = 'unknown'
        return {'value':f'{arg1["value"]} - {arg2["value"]}', 'type':varType}

    def mul(self, arg1, arg2):
        t1 = arg1['type']
        t2 = arg2['type']
        if t1 == 'int' and t2 == 'int':
            varType = 'int'
        elif t1 in {'float','int'} and t2 in {'float','int'}:
            varType = 'float'
        else:
            varType = 'unknown'
        return {'value':f'{arg1["value"]} * {arg2["value"]}', 'type':varType}

    def div(self, arg1, arg2):
        t1 = arg1['type']
        t2 = arg2['type']
        if t1 in {'float','int'} and t2 in {'float','int'}:
            varType = 'float'
        else:
            varType = 'unknown'
        return {'value':f'{arg1["value"]} / {arg2["value"]}', 'type':varType}
    
    def mod(self, arg1, arg2):
        return {'value':f'{arg1["value"]} % {arg2["value"]}', 'type':'int'}

    def exp(self, arg1, arg2):
        if arg1['type'] == 'int' and arg2['type'] == 'int':
            varType = 'int'
        else:
            varType = 'float'
        return {'value':f'pow({arg1["value"]}, {arg2["value"]})', 'type':'float'}

    def lessThan(self, arg1, arg2):
        return {'value':f'{arg1["value"]} < {arg2["value"]}', 'type':'bool'}

    def greaterThan(self, arg1, arg2):
        return {'value':f'{arg1["value"]} > {arg2["value"]}', 'type':'bool'}

    def equals(self, arg1, arg2):
        return {'value':f'{arg1["value"]} == {arg2["value"]}', 'type':'bool'}

    def greaterEqual(self, arg1, arg2):
        return {'value':f'{arg1["value"]} >= {arg2["value"]}', 'type':'bool'}
    
    def lessEqual(self, arg1, arg2):
        return {'value':f'{arg1["value"]} <= {arg2["value"]}', 'type':'bool'}

    def notEqual(self, arg1, arg2):
        return {'value':f'{arg1["value"]} != {arg2["value"]}', 'type':'bool'}

    def andOperator(self, arg1, arg2):
        return {'value':f'{arg1["value"]} && {arg2["value"]}', 'type':'bool'}

    def orOperator(self, arg1, arg2):
        return {'value':f'{arg1["value"]} || {arg2["value"]}', 'type':'bool'}

    def processGroup(self, token):
        expr = self.processExpr(token['expr'])
        if 'modifier' in token:
            op = token['modifier']
        else:
            op = ''
        return {'value':f'{op}({expr["value"]})', 'type':expr['type']}

    def isBlock(self, line):
        for b in self.block:
            if b in line and not line.startswith(self.commentSymbol):
                return True
        return False

    def run(self):
        print('Running')
