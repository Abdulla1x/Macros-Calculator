// Its own module so that a dynamic import (lib/motion.ts) can split Motion's
// animation features into a separate piece: LazyMotion renders `m` elements
// straight away and animates them once this arrives.
export { domAnimation as default } from 'motion/react'
