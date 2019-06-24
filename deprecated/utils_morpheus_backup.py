#!/usr/bin/env python

import re
import numpy
import random
import argparse
from collections import defaultdict
from tyrell import spec as S
from tyrell.interpreter import Interpreter, PostOrderInterpreter, GeneralError
from tyrell.enumerator import Enumerator, SmtEnumerator, RandomEnumerator, DesignatedEnumerator, RandomEnumeratorS, RandomEnumeratorFD
from tyrell.decider import Example, ExampleConstraintPruningDecider, ExampleDecider, TestDecider
from tyrell.synthesizer import Synthesizer
from tyrell.logger import get_logger
import rpy2.robjects as robjects
from sexpdata import Symbol
from tyrell import dsl as D
from typing import Callable, NamedTuple, List, Any

from scipy.spatial.distance import cosine

logger = get_logger('tyrell')

counter_ = 1

# load all words as candidate strings
with open("./words.txt","r") as f:
    TMP_WORDS = f.readlines()
TMP_WORDS = [i.strip() for i in TMP_WORDS]

robjects.r('''
    library(compare)
    library(dplyr)
    library(tidyr)
   ''')

## Common utils.
def get_collist(sel):
    sel_str = ",".join(sel)
    return "c(" + sel_str + ")"

def get_fresh_name():
    global counter_ 
    counter_ = counter_ + 1

    fresh_str = 'RET_DF' + str(counter_)
    return fresh_str

def get_fresh_col():
    global counter_ 
    counter_ = counter_ + 1

    fresh_str = 'COL' + str(counter_)
    return fresh_str

def get_type(df, index):
    _rscript = 'sapply({df_name}, class)[{pos}]'.format(df_name=df, pos=index)
    ret_val = robjects.r(_rscript)
    return ret_val[0]

def eq_r(actual, expect):
    _rscript = '''
    tmp1 <- sapply({lhs}, as.character)
    tmp2 <- sapply({rhs}, as.character)
    compare(tmp1, tmp2, ignoreOrder = TRUE, ignoreNames = TRUE)
    '''.format(lhs=actual, rhs=expect)
    # ignoreNames:TRUE, work for benchmark 23
    # logger.info(robjects.r(actual))
    # logger.info(robjects.r(expect))
    ret_val = robjects.r(_rscript)
    return True == ret_val[0][0]

def get_head(df):
    head = set()
    for h in df.colnames:
        head.add(h)

    return head

def get_content(df):
    content = set()
    for vec in df:
        for elem in vec:
            e_val = str(elem)
            content.add(e_val)

    return content

    
class MorpheusInterpreter(PostOrderInterpreter):
    def __init__(self):
        self.init_settings = {
            "MAX_VALUE": 100,
            "MIN_VALUE": -100,
            "MAX_ROW": 10, 
            # "MAX_COL": 6,
            "MAX_COL": 4, # set 2
        }
        self.random_dicts = {
            # the first 3 ms are dumb
            "string": lambda n,m: random.choices(TMP_WORDS, k=n),
            "float": lambda n,m: [random.uniform(self.init_settings["MIN_VALUE"],self.init_settings["MAX_VALUE"]) for _ in range(n)],
            "int": lambda n,m: random.choices(range(self.init_settings["MIN_VALUE"],self.init_settings["MAX_VALUE"]+1), k=n),
            # m cats, n instances
            "string_cat": lambda n,m: random.choices(
                random.choices(TMP_WORDS, k=m), 
                k=n,
            ),
            "int_cat": lambda n,m: random.choices(
                random.choices(range(self.init_settings["MIN_VALUE"],self.init_settings["MAX_VALUE"]+1), k=m),
                k=n,
            )
        }

    # method that generate random input table
    def random_table(self):
        dr = random.randint(5,self.init_settings["MAX_ROW"])
        # dc = random.randint(3,self.init_settings["MAX_COL"])
        dc = random.randint(2,self.init_settings["MAX_COL"]) # set2

        vlist = [
            self.random_dicts[
                random.choices(
                    ["string","float","int","string_cat","int_cat"],
                    weights=[1,2,4,2,2],
                    k=1,
                )[0]
            ](dr, random.choice([2,3,4,5]))
            for i in range(dc)
        ]

        # print(vlist)

        tmp_c = []
        for i in range(len(vlist)):
            tmp_c.append("OCOL{}=c(".format(i+1) + ",".join(["'{}'".format(j) if isinstance(j,str) else "{:.2f}".format(j) for j in vlist[i]]) + ")")

        ref_df_name = get_fresh_name()
        mr_script = "{} <- data.frame({}, stringsAsFactors=FALSE)".format(
            ref_df_name ,",".join(tmp_c),
        )
        # print("CODE:")
        # print(mr_script)
        try:
            ret_val = robjects.r(mr_script)
            return ref_df_name
        except:
            # logger.error('Error in generating random table...')
            raise GeneralError()

    def load_data_into_var(self, pdata, pvar):
        robjects.r("{} <- {}".format(pvar,pdata))

    '''
    perform a check on intermediate output
    if fail, the trainer can directly assign negative reward and terminate the current episode
    '''
    def outv_check(self, p_obj):
        try:
            # deal with
            # "data frame with 0 columns and 10 rows"
            dr = robjects.r('nrow({})'.format(p_obj))[0]
            dc = robjects.r('ncol({})'.format(p_obj))[0]
            if dr==0 or dc==0:
                return False
            else:
                np_obj = numpy.asarray(robjects.r(p_obj),dtype=numpy.object).T
        except Exception:
            return False

        try:
            ac = robjects.r("colnames({table})".format(table=p_obj))
        except Exception:
            return False

        for p in np_obj.flatten():
            if isinstance(p,str):
                if len(p)==0:
                    return False
                if "NA" in p:
                    return False
            elif isinstance(p,numpy.float):
                if numpy.isnan(p) or numpy.isinf(p):
                    return False
            else:
                return False

        return True


    # Single Input, Single Output
    def sanity_check(self, p_prog, p_example):
        # 0) no do nothing
        if p_example.input[0]==p_example.output:
            # print("==sanity violation #1==")
            return False

        # 0.1) don't be equal
        if eq_r(p_example.input[0],p_example.output):
            return False

        # 0.2) if mutate, make sure not dividing on the same columns
        # def rec_check_mutate(p_current):
        #     if p_current.name=="mutate" and p_current.children[2].data==p_current.children[3].data:
        #         return False
        #     for i in range(len(p_current.children)):
        #         if isinstance(p_current.children[i], D.node.ApplyNode):
        #             if rec_check_mutate(p_current.children[i])==False:
        #                 return False
        #     return True
        # if rec_check_mutate(p_prog)==False:
        #     return False

        
        # 1) no two consecutive same components
        def rec_check_con(p_current):
            for i in range(len(p_current.children)):
                if isinstance(p_current.children[i], D.node.ApplyNode):
                    if p_current.name==p_current.children[i].name:
                        # print("GOT")
                        # print("{},{}".format(p_current.name,p_current.children[i].name))
                        return True
                    elif rec_check_con(p_current.children[i])==True:
                        return True
            return False
        if isinstance(p_prog, D.node.ApplyNode):
            ret_val = rec_check_con(p_prog)
            if ret_val==True:
                # print("==sanity violation #2==")
                return False

        # 1.x) for testing select->gather sequence
        # enforce this sequence
        # the LAST component must be select
        # and the no duplicate rule will make sure the second is select
        # for set2 testing only
        if isinstance(p_prog, D.node.ApplyNode):
            if p_prog.name!="select":
                return False

        # 1.1) no group_by in the last call
        # if isinstance(p_prog, D.node.ApplyNode):
        #     if p_prog.name=="group_by" or p_prog.name=="neg_group_by":
        #         # print("==sanity violation #3==")
        #         return False

        # 2) result should have at least 1x1 cell
        mr_script = '''
            ncol({})<=0
        '''.format(p_example.output)
        ret_val = robjects.r(mr_script)
        if True==ret_val[0]:
            # print("==sanity violation #4==")
            return False
        mr_script = '''
            nrow({})<=0
        '''.format(p_example.output)
        ret_val = robjects.r(mr_script)
        if True==ret_val[0]:
            # print("==sanity violation #5==")
            return False

        # 3) no numeric NA in any cell
        # mr_script = '''
        #     any(sapply({},function(x) is.na(x)))
        # '''.format(p_example.output)
        # ret_val = robjects.r(mr_script)
        # if True==ret_val[0]:
        #     # has <NA> or empty string
        #     return False

        # 3.1) no infinity in any cell
        # mr_script = '''
        #     any(sapply({},function(x) is.infinite(x)))
        # '''.format(p_example.output)
        # ret_val = robjects.r(mr_script)
        # if True==ret_val[0]:
        #     # has infinity or empty string
        #     return False

        # 4) no empty string in any cell, require: no <NA> first
        # mr_script = '''
        #     any(sapply({},function(x) x==''))
        # '''.format(p_example.output)
        # ret_val = robjects.r(mr_script)
        # if True==ret_val[0]:
        #     # has empty string
        #     return False

        # # 5) no NA as substring in any cell
        # mr_script = '''
        #     any(sapply({},function(x) grepl("NA",x)))
        # '''.format(p_example.output)
        # ret_val = robjects.r(mr_script)
        # if True==ret_val[0]:
        #     # has empty string
        #     return False

        # 6) no "COL" as substring in any cell
        # This is to prevent gather->spread pattern that
        # compares COL value in cell
        # mr_script = '''
        #     any(sapply({},function(x) grepl("COL",x)))
        # '''.format(p_example.output)
        # ret_val = robjects.r(mr_script)
        # if True==ret_val[0]:
        #     # has empty string
        #     return False

        # print("==sanity check: True==")
        return True

    def print_obj(self,obj):
        print(robjects.r(obj))

    def print_cmp(self,obj):
        print(robjects.r("tmp1 <- sapply({}, as.character)".format(obj)))

    ## Concrete interpreter
    def eval_ColInt(self, v):
        return int(v)

    def eval_ColList(self, v):
        return v

    def eval_const(self, node, args):
        return args[0]

    def eval_select(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=1,
                cond=lambda x: max(list(map(lambda y: int(y), x))) <= n_cols,
                capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- select({table}, {cols})'.format(
                   ret_df=ret_df_name, table=args[0], cols=get_collist(args[1]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting select...')
            raise GeneralError()

    def eval_neg_select(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=1,
                cond=lambda x: max(list(map(lambda y: -int(y), x))) <= n_cols, # add negative
                capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- select({table}, {cols})'.format(
                   ret_df=ret_df_name, table=args[0], cols=get_collist(args[1]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting select...')
            raise GeneralError()

    def eval_unite(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        first_idx = int(args[1])
        self.assertArg(node, args,
                index=1,
                cond=lambda x: x <= n_cols,
                capture_indices=[0])
        self.assertArg(node, args,
                index=2,
                cond=lambda x: x <= n_cols and x != first_idx,
                capture_indices=[0, 1])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- unite({table}, {TMP}, {col1}, {col2})'.format(
                  ret_df=ret_df_name, table=args[0], TMP=get_fresh_col(), col1=str(args[1]), col2=str(args[2]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting unite...')
            raise GeneralError()

    def eval_filter(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=2,
                cond=lambda x: x <= n_cols,
                capture_indices=[0])
        self.assertArg(node, args,
                index=2,
                cond=lambda x: get_type(args[0], str(x)) != 'factor',
                capture_indices=[0])

        ret_df_name = get_fresh_name()

        _script = '{ret_df} <- {table} %>% filter(.[[{col}]] {op} {const})'.format(
                  ret_df=ret_df_name, table=args[0], op=args[1], col=str(args[2]), const=str(args[3]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting filter...')
            raise GeneralError()

    def eval_separate(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=1,
                cond=lambda x: x <= n_cols,
                capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- separate({table}, {col1}, c("{TMP1}", "{TMP2}"))'.format(
                  ret_df=ret_df_name, table=args[0], col1=str(args[1]), TMP1=get_fresh_col(), TMP2=get_fresh_col())
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting separate...')
            raise GeneralError()

    def eval_spread(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        first_idx = int(args[1])
        self.assertArg(node, args,
                index=1,
                cond=lambda x: x <= n_cols,
                capture_indices=[0])
        self.assertArg(node, args,
                index=2,
                cond=lambda x: x <= n_cols and x > first_idx,
                capture_indices=[0, 1])

        # print("PASS assertion.")
        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- spread({table}, {col1}, {col2})'.format(
                  ret_df=ret_df_name, table=args[0], col1=str(args[1]), col2=str(args[2]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # pritn("ERROR")
            # logger.error('Error in interpreting spread...')
            raise GeneralError()

    def eval_gather(self, node, args):
        # input("PAUSE")
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=1,
                cond=lambda x: max(list(map(lambda y: int(y), x))) <= n_cols,
                capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- gather({table}, KEY, VALUE, {cols})'.format(
                   ret_df=ret_df_name, table=args[0], cols=get_collist(args[1]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting gather...')
            raise GeneralError()

    def eval_neg_gather(self, node, args):
        # input("PAUSE")
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=1,
                cond=lambda x: max(list(map(lambda y: -int(y), x))) <= n_cols, # add negative
                capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- gather({table}, KEY, VALUE, {cols})'.format(
                   ret_df=ret_df_name, table=args[0], cols=get_collist(args[1]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting gather...')
            raise GeneralError()

    # NOTICE: use the scoped version: group_by_at to support column index
    def eval_group_by(self, node, args):

        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=1,
                cond=lambda x: max(list(map(lambda y: int(y), x))) <= n_cols,
                capture_indices=[0])
        
        # removing this assertion for benchmark#6
        # self.assertArg(node, args,
        #         index=1,
        #                cond=lambda x: len(x) == 1,
        #         capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- group_by_at({table}, {cols})'.format(
                   ret_df=ret_df_name, table=args[0], cols=get_collist(args[1]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting group_by...')
            raise GeneralError()

    # NOTICE: use the scoped version: group_by_at to support column index
    def eval_neg_group_by(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=1,
                cond=lambda x: max(list(map(lambda y: -int(y), x))) <= n_cols, # add negative
                capture_indices=[0])
        self.assertArg(node, args,
                index=1,
                       cond=lambda x: len(x) == 1,
                capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- group_by_at({table}, {cols})'.format(
                   ret_df=ret_df_name, table=args[0], cols=get_collist(args[1]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting group_by...')
            raise GeneralError()

    def eval_summarise(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=2,
                cond=lambda x: x <= n_cols,
                capture_indices=[0])
        self.assertArg(node, args,
                index=2,
                cond=lambda x: get_type(args[0], str(x)) == 'integer' or get_type(args[0], str(x)) == 'numeric',
                capture_indices=[0])

        # get column names
        colname = robjects.r("colnames({table})".format(table=args[0]))[args[2]-1]

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- {table} %>% summarise({TMP} = {aggr} (`{col}`))'.format(
                  ret_df=ret_df_name, table=args[0], TMP=get_fresh_col(), aggr=str(args[1]), col=colname)
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting summarise...')
            raise GeneralError()

    def eval_mutate(self, node, args):
        n_cols = robjects.r('ncol(' + args[0] + ')')[0]
        self.assertArg(node, args,
                index=2,
                cond=lambda x: x <= n_cols,
                capture_indices=[0])
        self.assertArg(node, args,
                index=3,
                cond=lambda x: x <= n_cols,
                capture_indices=[0])
        self.assertArg(node, args,
                index=2,
                cond=lambda x: get_type(args[0], str(x)) == 'numeric',
                capture_indices=[0])
        self.assertArg(node, args,
                index=3,
                cond=lambda x: get_type(args[0], str(x)) == 'numeric',
                capture_indices=[0])

        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- {table} %>% mutate({TMP}=.[[{col1}]] {op} .[[{col2}]])'.format(
                  ret_df=ret_df_name, table=args[0], TMP=get_fresh_col(), op=args[1], col1=str(args[2]), col2=str(args[3]))
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting mutate...')
            raise GeneralError()


    def eval_inner_join(self, node, args):
        ret_df_name = get_fresh_name()
        _script = '{ret_df} <- inner_join({t1}, {t2})'.format(
                  ret_df=ret_df_name, t1=args[0], t2=args[1])
        # print("CODE: {}".format(_script))
        try:
            ret_val = robjects.r(_script)
            return ret_df_name
        except:
            # logger.error('Error in interpreting innerjoin...')
            raise GeneralError()

    ## Abstract interpreter
    def apply_row(self, val):
        df = robjects.r(val)
        return df.nrow

    def apply_col(self, val):
        df = robjects.r(val)
        return df.ncol

    def apply_head(self, val):
        input_df = robjects.r('input0')
        curr_df = robjects.r(val)

        head_input = get_head(input_df)
        content_input = get_content(input_df)
        head_curr = get_head(curr_df)
        return len(head_curr - head_input - content_input)

    def apply_content(self, val):
        input_df = robjects.r('input0')
        curr_df = robjects.r(val)

        content_input = get_content(input_df)
        content_curr = get_content(curr_df)
        return len(content_curr - content_input)

'''
Chain Execution Single Input No Branch
'''
class MorpheusGenerator(object):
    _spec: S.TyrellSpec
    _interpreter: Interpreter
    _sfn: Callable[[Any,Any], bool]

    def __init__(self,
                 spec: S.TyrellSpec,
                 interpreter: Interpreter,
                 sfn: Callable[[Any,Any], bool] = lambda pr,ex:True):
        self._interpreter = interpreter
        self._spec = spec
        self._sfn = sfn

    def generate(self, fixed_depth, example, probs=(1,5)):
        tmp_enumerator = RandomEnumeratorFD(self._spec, fixed_depth = fixed_depth)
        _exp_cnt = 0
        while True:
            # print("trying...")
            try:
                tmp_prog = tmp_enumerator.next()
                # print("CAND:{}".format(tmp_prog))
                tmp_eval = self._interpreter.eval(
                    tmp_prog,
                    example.input,
                )
            # except StopIteration:
            #     print("STOP")
            #     continue
            except Exception:
                # print("EXCEPT")
                _exp_cnt += 1
                if _exp_cnt >= 10:
                    # exceed the limit consider changing example
                    return (None, None)
                continue
            tmp_example = Example(input=example.input, output=tmp_eval)
            if self._sfn(tmp_prog, tmp_example):
                    # print("YES")
                    return (
                        tmp_prog, 
                        tmp_example
                    )
            else:
                # important, also prevents infinite loop
                _exp_cnt += 1
                continue

def init_tbl(df_name, csv_loc):
    cmd = '''
    tbl_name <- read.csv(csv_location, check.names = FALSE)
    fctr.cols <- sapply(tbl_name, is.factor)
    int.cols <- sapply(tbl_name, is.integer)
    tbl_name[, fctr.cols] <- sapply(tbl_name[, fctr.cols], as.character)
    tbl_name[, int.cols] <- sapply(tbl_name[, int.cols], as.numeric)
    '''
    cmd = cmd.replace('tbl_name', df_name).replace('csv_location', '"'+ csv_loc + '"')
    robjects.r(cmd)
    return None


'''
========================================================================
========================================================================
==================== Starting Main Cambrian Version ====================
============================= abbr.: camb. =============================
========================================================================
========================================================================
'''

'''
helper for getting numpy object and simple metas (nrow, ncol)
'''
def camb_get_np_obj(p_obj):
    # get the table in numpy format
    try:
        # deal with
        # "data frame with 0 columns and 10 rows"
        dr = robjects.r('nrow({})'.format(p_obj))[0]
        dc = robjects.r('ncol({})'.format(p_obj))[0]
        if dr==0 or dc==0:
            np_obj = numpy.asarray([[]])
            dr = 0
            dc = 0
        else:
            np_obj = numpy.asarray(robjects.r(p_obj),dtype=numpy.object).T
    except Exception:
        np_obj = numpy.asarray([[]])
        dr = 0
        dc = 0
    return (np_obj, dr, dc)

def camb_get_col_names(p_obj):
    # just need to get column names
    try:
        ac = robjects.r("colnames({table})".format(table=p_obj))
    except Exception:
        # the same applies to this
        # then just create an empty list of column ignoreNames
        ac = []
    return ac

'''
a: cell2col
b: cell2cell
c: col2col
d: col2cell
'''
CAMB_NCOL = 20
CAMB_NROW = 50
CAMB_LIST = ["<PAD>","<aNEW>","<aDUP>","<aOUT>"]
CAMB_LIST +=["<bNEW>","<bDUP>","<bOUT>"]
CAMB_LIST +=["<cNEW>","<cDUP>","<cOUT>"]
CAMB_LIST +=["<dNEW>","<dDUP>","<dOUT>"]
CAMB_LIST += ["<aCOL_{}>".format(i) for i in range(CAMB_NCOL)]
CAMB_LIST += ["<bCOL_{}>".format(i) for i in range(CAMB_NCOL)]
CAMB_LIST += ["<cCOL_{}>".format(i) for i in range(CAMB_NCOL)]
CAMB_LIST += ["<dCOL_{}>".format(i) for i in range(CAMB_NCOL)]
CAMB_DICT = {CAMB_LIST[i]:i for i in range(len(CAMB_LIST))}

def camb_out_check(p_val):
    # check if the value belongs to <OUT>
    # True: it's out
    # False: it's NOT out
    if isinstance(p_val,numpy.float):
        if numpy.isnan(p_val) or numpy.isinf(p_val):
            # values that we do not want to put into set (unknown/uncared)
            return True
    return False

def camb_construct_column_dict(p_obj, p_r, p_c):
    # p_obj: a numpy array
    # construct the column dictionary
    # excluding some unknown/uncared values
    ret_dic = {}
    for j in range(p_c):
        tmp_set = set()
        for i in range(p_r):
            if camb_out_check(p_obj[i,j]):
                continue
            tmp_set.add(p_obj[i,j])
        ret_dic[j] = tmp_set
    return ret_dic

def camb_get_x2x_value(p_val, p_dic, p_prefix):
    # p_val: value of a numpy type to be converted to token
    # p_dic: dictionary that provides categories
    # p_prefix: a/b/c/d
    dfound = []
    for i in range(CAMB_NCOL):
        if i not in p_dic:
            # monotonically, break since it does not exist
            break
        if p_val in p_dic[i]:
            dfound.append(i)

    dtoken = None
    if len(dfound)==0:
        # could be <NEW> or <CMB> or <OUT>
        # we treat it as <NEW>/<OUT> temporarily
        if camb_out_check(p_val):
            dtoken = "<{}OUT>".format(p_prefix)
        else:
            dtoken = "<{}NEW>".format(p_prefix)
    elif len(dfound)==1:
        # if it's found, it can't be <OUT>
        dtoken = "<{}COL_{}>".format(p_prefix,dfound[0])
    else:
        # appear in more than 2
        dtoken = "<{}DUP>".format(p_prefix)

    return CAMB_DICT[dtoken]

'''
trying the new column markup method to create a
column markup map
'''
def camb_get_features(p0_obj, p1_obj, verbose=False):

    np0_obj, dr0, dc0 = camb_get_np_obj(p0_obj)
    np1_obj, dr1, dc1 = camb_get_np_obj(p1_obj)
    ac0 = camb_get_col_names(p0_obj)
    ac1 = camb_get_col_names(p1_obj)

    assert len(ac0)==dc0
    assert len(ac1)==dc1

    # a: cell2col
    # b: cell2cell
    # c: col2col
    # d: col2cell

    ab_dic = camb_construct_column_dict(np0_obj,dr0,dc0)
    # cell to col mapping
    amap = numpy.zeros((1,CAMB_NCOL)) # map for columns
    for i in range(min(CAMB_NCOL, dc1)):
        amap[0,i] = camb_get_x2x_value(ac1[i],ab_dic,"a")
    # cell to cell mapping
    bmap = numpy.zeros((CAMB_NROW,CAMB_NCOL)) # 0 is <PAD>
    for i in range(min(CAMB_NROW,dr1)):
        for j in range(min(CAMB_NCOL,dc1)):
            bmap[i,j] = camb_get_x2x_value(np1_obj[i,j],ab_dic,"b")

    # cd_dic = {i:set([ac0[i]]) for i in range(len(ac0))} # [ac0[i]] for entire string/value
    # # col to col mapping
    # cmap = numpy.zeros((1,CAMB_NCOL)) # map for columns
    # for i in range(min(CAMB_NCOL, dc1)):
    #     cmap[0,i] = camb_get_x2x_value(ac1[i],cd_dic,"c")
    # # col to cell mapping
    # dmap = numpy.zeros((CAMB_NROW,CAMB_NCOL)) # 0 is <PAD>
    # for i in range(min(CAMB_NROW,dr1)):
    #     for j in range(min(CAMB_NCOL,dc1)):
    #         dmap[i,j] = camb_get_x2x_value(np1_obj[i,j],cd_dic,"d")

    # rmap = numpy.vstack((amap, bmap, cmap, dmap))
    rmap = numpy.vstack((amap, bmap))

    if verbose:
        print(rmap)

    return rmap
    # (row, col) -> (col, row) / (dim, maxlen)
    # return dmap.T
    # return dmap.flatten().tolist()
    # return dmap[0,:].flatten().tolist()
