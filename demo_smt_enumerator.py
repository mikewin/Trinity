#!/usr/bin/env python

import spec as S
from interpreter import PostOrderInterpreter
from enumerator import SmtEnumerator
from synthesizer import ExampleSynthesizer, Example
import logger

logger = logger.get('tyrell')

toy_spec_str = '''
enum SmallInt {
  "0", "1", "2", "3"
}
value Int;
value Empty;

program Toy(Int, Int) -> Int;
func const: Int -> SmallInt;
func plus: Int -> Int, Int;
func minus: Int -> Int, Int;
func mult: Int -> Int, Int;
func empty: Empty -> Empty;
'''


class ToyInterpreter(PostOrderInterpreter):
    def eval_SmallInt(self, v):
        return int(v)

    def eval_const(self, node, args):
        return args[0]

    def eval_plus(self, node, args):
        return args[0] + args[1]

    def eval_minus(self, node, args):
        return args[0] - args[1]

    def eval_mult(self, node, args):
        return args[0] * args[1]


def main():
    logger.info('Parsing Spec...')
    spec = S.parse(toy_spec_str)
    logger.info('Parsing succeeded')

    logger.info('Building synthesizer...')
    synthesizer = ExampleSynthesizer(
        enumerator=SmtEnumerator(spec, depth=3, loc=2),
        interpreter=ToyInterpreter(),
        examples=[
            # we want to synthesize the program (x-y)*y (depth=3, loc=2)
            # which is also equivalent to x*y-y*y (depth=3, loc=3)
            Example(input=[4, 3], output=3),
            Example(input=[6, 3], output=9),
            Example(input=[1, 2], output=-2),
            Example(input=[1, 1], output=0),
        ]
    )
    logger.info('Synthesizing programs...')

    prog = synthesizer.synthesize()
    if prog is not None:
        logger.info('Solution found: {}'.format(prog))
    else:
        logger.info('Solution not found!')


if __name__ == '__main__':
    logger.setLevel('DEBUG')
    main()