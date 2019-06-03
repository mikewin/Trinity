from sexpdata import Symbol

solutions = {
    1: [Symbol('spread'),
            [Symbol('unite'),
                [Symbol('neg_gather'),
                    [Symbol('@param'),0],
                    [Symbol('ColNegList'),[-1,-4]],
                ],
                [Symbol('ColInt'),3],
                [Symbol('ColInt'),1],
            ],
            [Symbol('ColInt'),1],
            [Symbol('ColInt'),3],
        ],
    2: [Symbol('spread'),
        [Symbol('unite'),
            [Symbol('gather'),
                [Symbol('@param'),0],
                [Symbol('ColList'),[3,4]],
            ],
            [Symbol('ColInt'),2],
            [Symbol('ColInt'),3],
        ],
        [Symbol('ColInt'),2],
        [Symbol('ColInt'),3],
    ],
    3: [Symbol('spread'),
        [Symbol('unite'),
            [Symbol('gather'),
                [Symbol('@param'),0],
                [Symbol('ColList'),[3,4]],
            ],
            [Symbol('ColInt'),2],
            [Symbol('ColInt'),3],
        ],
        [Symbol('ColInt'),2],
        [Symbol('ColInt'),3],
    ],
    4: [Symbol('spread'),
        [Symbol('unite'),
            [Symbol('gather'),
                [Symbol('@param'),0],
                [Symbol('ColList'),[3,4]],
            ],
            [Symbol('ColInt'),3],
            [Symbol('ColInt'),2],
        ],
        [Symbol('ColInt'),2],
        [Symbol('ColInt'),3],
    ],
    5: [Symbol('neg_select'),
        [Symbol('separate'),
            [Symbol('neg_gather'),
                [Symbol('@param'),0],
                [Symbol('ColNegList'),[-1,-2]]
            ],
            [Symbol('ColInt'),3],
        ],
        [Symbol('ColNegList'),[-3]],
    ],
    6: [Symbol('summarise'),
        [Symbol('group_by'),
            [Symbol('separate'),
                [Symbol('neg_gather'),
                    [Symbol('@param'),0],
                    [Symbol('ColNegList'),[-1,-5]],
                ],
                [Symbol('ColInt'),3],
            ],
            [Symbol('ColList'),[1,3]],
        ],
        [Symbol('Aggr'),"sum"],
        [Symbol('ColInt'),5],
    ],
    7: [Symbol('neg_select'),
        [Symbol('mutate'),
            [Symbol('spread'),
                [Symbol('separate'),
                    [Symbol('neg_gather'),
                        [Symbol('@param'),0],
                        [Symbol('ColNegList'),[-1,-6]],
                    ],
                    [Symbol('ColInt'),3],
                ],
                [Symbol('ColInt'),3],
                [Symbol('ColInt'),5],
            ],
            [Symbol('NumFunc'),"/"],
            [Symbol('ColInt'),4],
            [Symbol('ColInt'),5],
        ],
        [Symbol("ColNegList"),[-2]],
    ],
    8: [Symbol('summarise'),
        [Symbol('group_by'),
            [Symbol('inner_join'),
                [Symbol('summarise'),
                    [Symbol('group_by'),
                        [Symbol('@param'),0],
                        [Symbol('ColList'),[1]],
                    ],
                    [Symbol('Aggr'),"mean"],
                    [Symbol('ColInt'),4],
                ],
                [Symbol('@param'),0],
            ],
            [Symbol('ColList'),[1,2]],
        ],
        [Symbol('Aggr'),"mean"],
        [Symbol('ColInt'),4],
    ],
    9: [Symbol('neg_select'),
        [Symbol('mutate'),
            [Symbol('spread'),
                [Symbol('@param'),0],
                [Symbol('ColInt'),3],
                [Symbol('ColInt'),4],
            ],
            [Symbol('NumFunc'),"/"],
            [Symbol('ColInt'),3],
            [Symbol('ColInt'),4],
        ],
        [Symbol('ColNegList'),[-3,-4]],
    ],
    10:[Symbol('neg_select'),
        [Symbol('gather'),
            [Symbol('separate'),
                [Symbol('@param'),0],
                [Symbol('ColInt'),4],
            ],
            [Symbol('ColList'),[4,5]],
        ],
        [Symbol('ColNegList'),[-4]],
    ],
    
    "test": [Symbol('spread'),
            [Symbol('unite'),
                [Symbol('neg_gather'),
                    [Symbol('@param'),0],
                    [Symbol('ColNegList'),['-1','-4']],
                ],
                [Symbol('ColInt'),3],
                [Symbol('ColInt'),1],
            ],
            [Symbol('ColInt'),1],
            [Symbol('ColInt'),8],
        ],
}