import { prisma } from "../../lib/prisma";

export async function listPostsForFamily(familyId: string) {
  const posts = await prisma.familyPost.findMany({
    where: { familyId },
    include: {
      author: true,
      comments: {
        include: { author: true },
        orderBy: { createdAt: "asc" }
      },
      likes: true
    },
    orderBy: { createdAt: "desc" }
  });

  return posts.map((post) => ({
    id: post.id,
    familyId: post.familyId,
    body: post.body,
    mediaUrl: post.mediaUrl,
    createdAt: post.createdAt,
    author: {
      id: post.author.id,
      displayName: post.author.displayName
    },
    likeCount: post.likes.length,
    commentCount: post.comments.length,
    comments: post.comments.map((comment) => ({
      id: comment.id,
      body: comment.body,
      author: {
        id: comment.author.id,
        displayName: comment.author.displayName
      }
    }))
  }));
}
