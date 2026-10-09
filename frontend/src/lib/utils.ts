import { createCn } from 'cn/config'

/** Join class names and let a later Tailwind class override an earlier one of
 *  the same kind: `cn('px-2', isWide && 'px-4')` -> 'px-4'. shadcn/ui's
 *  components (src/ui/) all go through it.
 *
 *  ⚠ It has to be told about this app's own utilities. It decides which
 *  classes conflict by their prefix, and with no configuration it reads every
 *  `text-<word>` as a colour -- so `cn('text-ink text-field-label')` returned
 *  just 'text-field-label' and silently dropped the colour. The type styles
 *  (index.css @utility) are font sizes and the extra radii are radii, so a
 *  type style and a colour both survive, and two type styles still resolve
 *  to the later one. Add a name here whenever index.css gains a text-* or
 *  rounded-* that is not a colour; tests/cn.test.ts holds the list. */
export const cn = createCn({
  extend: {
    classGroups: {
      'font-size': [
        {
          text: [
            'display-number',
            'field-number',
            'row-number',
            'title',
            'body',
            'small',
            'field-label',
          ],
        },
      ],
      rounded: [{ rounded: ['tag', 'control', 'log', 'sheet', 'card'] }],
    },
  },
})
