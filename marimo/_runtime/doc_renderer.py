import __future__

import builtins
import importlib._bootstrap
import importlib._bootstrap_external
import importlib.machinery
import importlib.util
import inspect
import io
import os
import pkgutil
import platform
import pydoc
import re
import sys
import sysconfig
import time
import tokenize
import urllib.parse
import warnings
from collections import deque
from reprlib import Repr
from traceback import format_exception_only
import jedi  # type: ignore # noqa: F401
import jedi.api  # type: ignore # noqa: F401


class MarimoTextDoc(pydoc.Doc):
    # ------------------------------------------- HTML formatting utilities
    _repr_instance = pydoc.HTMLRepr()
    repr = _repr_instance.repr
    escape = _repr_instance.escape

    def __init__(self) -> None:
        super().__init__()

    _future_feature_names = set(__future__.all_feature_names)

    def visiblename(self,name, all=None, obj=None):
        """Decide whether to show documentation on a variable."""
        # Certain special names are redundant or internal.
        # XXX Remove __initializing__?
        if name in {'__author__', '__builtins__', '__cached__', '__credits__',
                    '__date__', '__doc__', '__file__', '__spec__',
                    '__loader__', '__module__', '__name__', '__package__',
                    '__path__', '__qualname__', '__slots__', '__version__'}:
            return False
        # Private names are hidden, but special names are displayed.
        if name.startswith('__') and name.endswith('__'): return True
        # Namedtuples have public fields and methods with a single leading underscore
        if name.startswith('_') and hasattr(obj, '_fields'):
            return True
        # Ignore __future__ imports.
        if obj is not __future__ and name in self._future_feature_names:
            if isinstance(getattr(obj, name, None), __future__._Feature):
                return False
        if all is not None:
            # only document that which the programmer exported in __all__
            return name in all
        else:
            return not name.startswith('_')
        
    def cram(self, text, maxlen):
        """Omit part of a string if needed to make it fit in a maximum length."""
        if len(text) > maxlen:
            pre = max(0, (maxlen-3)//2)
            post = max(0, maxlen-3-pre)
            return text[:pre] + '...' + text[len(text)-post:]
        return text

    def section(self, title, cls, contents, width=6,
                prelude='', marginalia=None, gap='&nbsp;'):
        """Format a section with a heading."""
        if not contents:
            return ''

        if marginalia is None:
            marginalia = '<span class="code">' + '&nbsp;' * width + '</span>'

        result = f'''
        <div class="section {cls}-decor">
            <h3 class="section-title heading-text">{title}</h3>
        '''

        if prelude:
            result += f'<div class="prelude">{prelude}</div>'

        result += f'''
            <div class="section-content">
                {marginalia}
                <div class="singlecolumn">{contents}</div>
            </div>
        </div>
        '''

        return result

    def bigsection(self, title, *args):
        """Format a section with a big heading."""
        title = '<strong class="bigsection">%s</strong>' % title
        return self.section(title, *args)

    def preformat(self, text):
        """Format literal preformatted text."""
        text = self.escape(text.expandtabs())
        return pydoc.replace(text, '\n\n', '\n \n', '\n\n', '\n \n',
                             ' ', '&nbsp;', '\n', '<br>\n')

    def multicolumn(self, list, format=str):
        """Format a list of items into a multi-column list."""
        if not list:
            return ''

        result = ''
        num_items = len(list)
        num_columns = min(4, num_items)
        rows = (num_items + num_columns - 1) // num_columns

        for col in range(num_columns):
            start_index = col * rows
            end_index = min((col + 1) * rows, num_items)
            
            if start_index < num_items:
                result += '<td class="multicolumn">'
                for i in range(start_index, end_index):
                    result += format(list[i]) + '<br>\n'
                result += '</td>'

        return '<table><tr>%s</tr></table>' % result

    def simplelist(self, items, format=str):
        """Format a list of items into a simple HTML list."""
        if not list:
            return ''

        result = '<ul>'
        for item in items:
            result += '<li>' + format(item) + '</li>'
        result += '</ul>'
        return result

    def grey(self, text): return '<span class="grey">%s</span>' % text

    def namelink(self, name, *dicts):
        """Make a link for an identifier, given name-to-URL mappings."""
        for dict in dicts:
            if name in dict:
                return '<a href="%s">%s</a>' % (dict[name], name)
        return name

    def classlink(self, object, modname, cdict=None):
        """Make a link for a class."""
        # name, module = object.__name__, sys.modules.get(object.__module__)
        # if hasattr(module, name) and getattr(module, name) is object:
        #     return '<a href="%s.html#%s">%s</a>' % (
        #         module.__name__, name, pydoc.classname(object, modname))
        alias = cdict.get(object) if cdict else None
        if alias:
            return f"<b>{alias}</b> ({pydoc.classname(object, modname)})"
        else:
            return pydoc.classname(object, modname)

    def parentlink(self, object, modname):
        """Make a link for the enclosing class or module."""
        link = None
        name, module = object.__name__, sys.modules.get(object.__module__)
        if hasattr(module, name) and getattr(module, name) is object:
            if '.' in object.__qualname__:
                name = object.__qualname__.rpartition('.')[0]
                if object.__module__ != modname:
                    link = '%s.html#%s' % (module.__name__, name)
                else:
                    link = '#%s' % name
            else:
                if object.__module__ != modname:
                    link = '%s.html' % module.__name__
        if link:
            return '<a href="%s">%s</a>' % (link, pydoc.parentname(object, modname))
        else:
            return pydoc.parentname(object, modname)

    def modulelink(self, object):
        """Make a link for a module."""
        return object[0] # TODO: we can generate special links which live docs can switch to in the future
        return '<a href="%s.html">%s</a>' % (object.__name__, object.__name__)

    def modpkglink(self, modpkginfo):
        """Make a link for a module or package to display in an index."""
        name, path, ispackage, shadowed = modpkginfo
        if shadowed:
            return self.grey(name)
        if path:
            url = '%s.%s.html' % (path, name)
        else:
            url = '%s.html' % name
        if ispackage:
            text = '<strong>%s</strong>&nbsp;(package)' % name
        else:
            text = name

        return text # TODO: we can generate special links which live docs can switch to in the future
        #return '<a href="%s">%s</a>' % (url, text)

    def filelink(self, url, path):
        """Make a link to source file."""
        return '<a href="file:%s">%s</a>' % (url, path)

    def markup(self, text, escape=None, funcs={}, classes={}, methods={}):
        """Mark up some plain text, given a context of symbols to look for.
        Each context dictionary maps object names to anchor names."""
        escape = escape or self.escape
        results = []
        here = 0
        pattern = re.compile(r'\b((http|https|ftp)://\S+[\w/]|'
                                r'RFC[- ]?(\d+)|'
                                r'PEP[- ]?(\d+)|'
                                r'(self\.)?(\w+))')
        while match := pattern.search(text, here):
            start, end = match.span()
            results.append(escape(text[here:start]))

            all, scheme, rfc, pep, selfdot, name = match.groups()
            if scheme:
                url = escape(all).replace('"', '&quot;')
                results.append('<a href="%s">%s</a>' % (url, url))
            elif rfc:
                url = 'https://www.rfc-editor.org/rfc/rfc%d.txt' % int(rfc)
                results.append('<a href="%s">%s</a>' % (url, escape(all)))
            elif pep:
                url = 'https://peps.python.org/pep-%04d/' % int(pep)
                results.append('<a href="%s">%s</a>' % (url, escape(all)))
            elif selfdot:
                # Create a link for methods like 'self.method(...)'
                # and use <strong> for attributes like 'self.attr'
                if text[end:end+1] == '(':
                    results.append('self.' + self.namelink(name, methods))
                else:
                    results.append('self.<strong>%s</strong>' % name)
            elif text[end:end+1] == '(':
                results.append(self.namelink(name, methods, funcs, classes))
            else:
                results.append(self.namelink(name, classes))
            here = end
        results.append(escape(text[here:]))
        return ''.join(results)

    # ---------------------------------------------- type-specific routines

    def formattree(self, tree, modname, cdict, parent=None):
        """Produce HTML for a class tree as given by inspect.getclasstree()."""
        if not parent:
            result = '<div style="border: 1px solid #ccc; padding: 10px; font-size: 13px;">'
        else:
            result = '<div style="padding: 10px; font-size: 13px;">'
        for entry in tree:
            if isinstance(entry, tuple):
                c, bases = entry
                result += '<div style="padding-left: {}em;">'.format(2 * (len(c.__qualname__.split('.')) - 1))
                result += self.classlink(c, modname, cdict)
                if bases and bases != (parent,):
                    parents = []
                    for base in bases:
                        parents.append(self.classlink(base, modname, cdict))
                    result += '(' + ', '.join(parents) + ')'
                result += '</div>\n'
            elif isinstance(entry, list):
                result += self.formattree(entry, modname, cdict, c)

        result += '</div>'
        return result



    def docmodule(self, completion: jedi.api.classes.BaseName):
        """Produce HTML documentation for a module object."""
        result = ""
        # classes, cdict = [], {}
        # for key, value in inspect.getmembers(object, inspect.isclass):
        #     # if __all__ exists, believe it.  Otherwise use old heuristic.
        #     if (all is not None or
        #         (inspect.getmodule(value) or object) is object):
        #         if pydoc.visiblename(key, all, object):
        #             classes.append((key, value))
        #             cdict[key] = cdict[value] = name + "." + key

        # funcs, fdict = [], {}
        # for key, value in inspect.getmembers(object, inspect.isroutine):
        #     # if __all__ exists, believe it.  Otherwise use old heuristic.
        #     if (all is not None or
        #         inspect.isbuiltin(value) or inspect.getmodule(value) is object):
        #         if pydoc.visiblename(key, all, object):
        #             funcs.append((key, value))
        #             fdict[key] = '#-' + key
        #             if inspect.isfunction(value): fdict[value] = fdict[key]
        # data = []
        # for key, value in inspect.getmembers(object, pydoc.isdata):
        #    # if (key == '__all__'):
        #    #     continue
        #     if pydoc.visiblename(key, all, object):
        #         data.append((key, value))


        all_defined_names = completion.goto()[0].defined_names()

        modules = [name.name for name in all_defined_names if name.type == 'module' and self.visiblename(name.name)]
        modules.sort()
        
        contents = self.multicolumn(modules)
        result = result + self.bigsection(
            'Modules', 'pkg-content', contents)
        
        classes = [name.name for name in all_defined_names if name.type == 'class' and self.visiblename(name.name)]
        classes.sort(key=str.lower)
            
        if classes:
            result = result + self.bigsection(
                'Classes', 'classes', self.multicolumn(classes))

        funcs = [name.name for name in all_defined_names if name.type == 'function' and self.visiblename(name.name)]
        funcs.sort(key=str.lower)

        if funcs:
            result = result + self.bigsection(
                'Functions', 'functions', self.multicolumn(funcs))
        
        datas_dict = {}
        for name in all_defined_names:
            if name.type == 'statement' and self.visiblename(name.name):
                desc = name.description
                if desc.startswith(name.name + ' = '):
                    datas_dict[name.name] = self.escape(name.name)
                if desc.startswith("del"):
                    datas_dict.pop(name.name, None)
        datas = list(datas_dict.values())
        datas.sort(key=str.lower)
        if datas:
            result = result + self.bigsection(
                'Data', 'data', '<br>\n'.join(datas))
    
        return result

    def docclass(self, object, name=None, mod=None, funcs={}, classes={},
                 *ignored):
        """Produce HTML documentation for a class object."""
        realname = object.__name__
        name = name or realname
        bases = object.__bases__

        contents = []
        push = contents.append

        # Cute little class to pump out a horizontal rule between sections.
        class HorizontalRule:
            def __init__(self):
                self.needone = 0
            def maybe(self):
                if self.needone:
                    push('<hr>\n')
                self.needone = 1
        hr = HorizontalRule()

        # List the mro, if non-trivial.
        mro = deque(inspect.getmro(object))
        if len(mro) > 2:
            hr.maybe()
            push('<dl><dt>Method resolution order:</dt>\n')
            for base in mro:
                push('<dd>%s</dd>\n' % self.classlink(base,
                                                      object.__module__))
            push('</dl>\n')

        def spill(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate)
            if ok:
                hr.maybe()
                push(msg)
                for name, kind, homecls, value in ok:
                    try:
                        value = getattr(object, name)
                    except Exception:
                        # Some descriptors may meet a failure in their __get__.
                        # (bug #1785)
                        push(self.docdata(value, name, mod))
                    else:
                        push(self.document(value, name, mod,
                                        funcs, classes, mdict, object, homecls))
                    push('\n')
            return attrs

        def spilldescriptors(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate)
            if ok:
                hr.maybe()
                push(msg)
                for name, kind, homecls, value in ok:
                    push(self.docdata(value, name, mod))
            return attrs

        def spilldata(msg, attrs, predicate):
            ok, attrs = pydoc._split_list(attrs, predicate)
            if ok:
                hr.maybe()
                push(msg)
                for name, kind, homecls, value in ok:
                    base = self.docother(getattr(object, name), name, mod)
                    doc = pydoc.getdoc(value)
                    if not doc:
                        push('<dl><dt>%s</dl>\n' % base)
                    else:
                        doc = self.markup(pydoc.getdoc(value), self.preformat,
                                          funcs, classes, mdict)
                        doc = '<dd><span class="code">%s</span>' % doc
                        push('<dl><dt>%s%s</dl>\n' % (base, doc))
                    push('\n')
            return attrs

        attrs = [(name, kind, cls, value)
                 for name, kind, cls, value in pydoc.classify_class_attrs(object)
                 if pydoc.visiblename(name, obj=object)]

        mdict = {}
        for key, kind, homecls, value in attrs:
            mdict[key] = anchor = '#' + name + '-' + key
            try:
                value = getattr(object, name)
            except Exception:
                # Some descriptors may meet a failure in their __get__.
                # (bug #1785)
                pass
            try:
                # The value may not be hashable (e.g., a data attr with
                # a dict or list value).
                mdict[value] = anchor
            except TypeError:
                pass

        while attrs:
            if mro:
                thisclass = mro.popleft()
            else:
                thisclass = attrs[0][2]
            attrs, inherited = pydoc._split_list(attrs, lambda t: t[2] is thisclass)

            if object is not builtins.object and thisclass is builtins.object:
                attrs = inherited
                continue
            elif thisclass is object:
                tag = 'defined here'
            else:
                tag = 'inherited from %s' % self.classlink(thisclass,
                                                           object.__module__)
            tag += ':<br>\n'

            pydoc.sort_attributes(attrs, object)

            # Pump out the attrs, segregated by kind.
            attrs = spill('Methods %s' % tag, attrs,
                          lambda t: t[1] == 'method')
            attrs = spill('Class methods %s' % tag, attrs,
                          lambda t: t[1] == 'class method')
            attrs = spill('Static methods %s' % tag, attrs,
                          lambda t: t[1] == 'static method')
            attrs = spilldescriptors("Readonly properties %s" % tag, attrs,
                                     lambda t: t[1] == 'readonly property')
            attrs = spilldescriptors('Data descriptors %s' % tag, attrs,
                                     lambda t: t[1] == 'data descriptor')
            attrs = spilldata('Data and other attributes %s' % tag, attrs,
                              lambda t: t[1] == 'data')
            assert attrs == []
            attrs = inherited

        contents = ''.join(contents)

        if name == realname:
            title = '<a name="%s">class <strong>%s</strong></a>' % (
                name, realname)
        else:
            title = '<strong>%s</strong> = <a name="%s">class %s</a>' % (
                name, name, realname)
        if bases:
            parents = []
            for base in bases:
                parents.append(self.classlink(base, object.__module__))
            title = title + '(%s)' % ', '.join(parents)

        decl = ''
        try:
            signature = inspect.signature(object)
        except (ValueError, TypeError):
            signature = None
        if signature:
            argspec = str(signature)
            if argspec and argspec != '()':
                decl = name + self.escape(argspec) + '\n\n'

        doc = pydoc.getdoc(object)
        if decl:
            doc = decl + (doc or '')
        doc = self.markup(doc, self.preformat, funcs, classes, mdict)
        doc = doc and '<span class="code">%s<br>&nbsp;</span>' % doc

        return self.section(title, 'title', contents, 3, doc)

    def formatvalue(self, object):
        """Format an argument default value as text."""
        return self.grey('=' + self.repr(object))

    def docroutine(self, object, name=None, mod=None,
                   funcs={}, classes={}, methods={}, cl=None, homecls=None):
        """Produce HTML documentation for a function or method object."""
        realname = object.__name__
        name = name or realname
        if homecls is None:
            homecls = cl
        anchor = ('' if cl is None else cl.__name__) + '-' + name
        note = ''
        skipdocs = False
        imfunc = None
        if pydoc._is_bound_method(object):
            imself = object.__self__
            if imself is cl:
                imfunc = getattr(object, '__func__', None)
            elif inspect.isclass(imself):
                note = ' class method of %s' % self.classlink(imself, mod)
            else:
                note = ' method of %s instance' % self.classlink(
                    imself.__class__, mod)
        elif (inspect.ismethoddescriptor(object) or
              inspect.ismethodwrapper(object)):
            try:
                objclass = object.__objclass__
            except AttributeError:
                pass
            else:
                if cl is None:
                    note = ' unbound %s method' % self.classlink(objclass, mod)
                elif objclass is not homecls:
                    note = ' from ' + self.classlink(objclass, mod)
        else:
            imfunc = object
        if inspect.isfunction(imfunc) and homecls is not None and (
            imfunc.__module__ != homecls.__module__ or
            imfunc.__qualname__ != homecls.__qualname__ + '.' + realname):
            pname = self.parentlink(imfunc, mod)
            if pname:
                note = ' from %s' % pname

        if (inspect.iscoroutinefunction(object) or
                inspect.isasyncgenfunction(object)):
            asyncqualifier = 'async '
        else:
            asyncqualifier = ''

        if name == realname:
            title = '<a name="%s"><strong>%s</strong></a>' % (anchor, realname)
        else:
            if (cl is not None and
                inspect.getattr_static(cl, realname, []) is object):
                reallink = '<a href="#%s">%s</a>' % (
                    cl.__name__ + '-' + realname, realname)
                skipdocs = True
                if note.startswith(' from '):
                    note = ''
            else:
                reallink = realname
            title = '<a name="%s"><strong>%s</strong></a> = %s' % (
                anchor, name, reallink)
        argspec = None
        if inspect.isroutine(object):
            try:
                signature = inspect.signature(object)
            except (ValueError, TypeError):
                signature = None
            if signature:
                argspec = str(signature)
                if realname == '<lambda>':
                    title = '<strong>%s</strong> <em>lambda</em> ' % name
                    # XXX lambda's won't usually have func_annotations['return']
                    # since the syntax doesn't support but it is possible.
                    # So removing parentheses isn't truly safe.
                    if not object.__annotations__:
                        argspec = argspec[1:-1] # remove parentheses
        if not argspec:
            argspec = '(...)'

        decl = asyncqualifier + title + self.escape(argspec) + (note and
               self.grey('<span class="heading-text">%s</span>' % note))

        if skipdocs:
            return '<dl><dt>%s</dt></dl>\n' % decl
        else:
            doc = self.markup(
                pydoc.getdoc(object), self.preformat, funcs, classes, methods)
            doc = doc and '<dd><span class="code">%s</span></dd>' % doc
            return '<dl><dt>%s</dt>%s</dl>\n' % (decl, doc)

    def docdata(self, object, name=None, mod=None, cl=None, *ignored):
        """Produce html documentation for a data descriptor."""
        results = []
        push = results.append

        if name:
            push('<dl><dt><strong>%s</strong></dt>\n' % name)
        doc = self.markup(pydoc.getdoc(object), self.preformat)
        if doc:
            push('<dd><span class="code">%s</span></dd>\n' % doc)
        push('</dl>\n')

        return ''.join(results)

    docproperty = docdata

    def docother(self, object, name=None, mod=None, *ignored):
        """Produce HTML documentation for a data object."""
        lhs = name and '<strong>%s</strong> = ' % name or ''
        return lhs + self.repr(object)

    def index(self, dir, shadowed=None):
        """Generate an HTML index for a directory of modules."""
        modpkgs = []
        if shadowed is None: shadowed = {}
        for importer, name, ispkg in pkgutil.iter_modules([dir]):
            if any((0xD800 <= ord(ch) <= 0xDFFF) for ch in name):
                # ignore a module if its name contains a surrogate character
                continue
            modpkgs.append((name, '', ispkg, name in shadowed))
            shadowed[name] = 1

        modpkgs.sort()
        contents = self.multicolumn(modpkgs, self.modpkglink)
        return self.bigsection(dir, 'index', contents)
