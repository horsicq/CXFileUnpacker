/* SPDX-License-Identifier: GPL-3.0-or-later.
 * Isolated SA grammar probe. ZAP callbacks supply independently constructed
 * registry/layout arrays; actual producer integration uses the real helper. */
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <stdarg.h>
typedef uint8_t grub_uint8_t;typedef uint16_t grub_uint16_t;typedef uint32_t grub_uint32_t;typedef uint64_t grub_uint64_t;typedef size_t grub_size_t;typedef int grub_err_t;typedef int grub_zfs_endian_t;
enum {GRUB_ERR_NONE,GRUB_ERR_BAD_FS,GRUB_ERR_FILE_NOT_FOUND,GRUB_ERR_OUT_OF_MEMORY};enum{GRUB_ZFS_LITTLE_ENDIAN=-1,GRUB_ZFS_BIG_ENDIAN=0};static int grub_errno;
static uint16_t swap16(uint16_t n){return (uint16_t)(n<<8)|(n>>8);}static uint32_t swap32(uint32_t n){return ((n&255)<<24)|((n&65280)<<8)|((n>>8)&65280)|(n>>24);}
static uint16_t grub_get_unaligned16(const void *p){uint16_t n;memcpy(&n,p,2);return n;}static uint32_t grub_get_unaligned32(const void *p){uint32_t n;memcpy(&n,p,4);return n;}
#define grub_be_to_cpu16 swap16
#define grub_le_to_cpu32(n) (n)
#define grub_be_to_cpu32 swap32
#define grub_zfs_to_cpu16(n,e) ((e)==0?swap16(n):(n))
#define grub_strcmp strcmp
#define grub_strlen strlen
#define grub_memcpy memcpy
#define grub_memcmp memcmp
#define grub_memset memset
#define grub_snprintf snprintf
#define grub_free free
static void *grub_malloc(size_t n){void *p=malloc(n);if(!p)grub_errno=GRUB_ERR_OUT_OF_MEMORY;return p;}
static grub_err_t grub_error(grub_err_t e,const char *message,...){(void)message;grub_errno=e;return e;}
typedef struct{uint8_t b[128];}blkptr_t;
typedef struct{uint8_t dn_type,dn_indblkshift,dn_nlevels,dn_nblkptr,dn_bonustype,dn_checksum,dn_compress,dn_flags;uint16_t dn_datablkszsec,dn_bonuslen;uint8_t pad[4];uint64_t maxblkid,used,pad3[4];blkptr_t ptr;uint8_t bonus[192];blkptr_t dn_spill;} dnode_phys_t;
typedef struct{dnode_phys_t dn;grub_zfs_endian_t endian;}dnode_end_t;
struct subvolume{dnode_end_t mdn;};struct grub_zfs_data{int dummy;};struct grub_zfs_dir_ctx{int dummy;};
#define MASTER_NODE_OBJ 1
#define DMU_OT_MASTER_NODE 21
#define ZFS_SA_ATTRS "SA_ATTRS"
#define DNODE_SIZE 512
#define DNODE_CORE_SIZE 64
#define DN_MAX_NBLKPTR 3
#define DNODE_FLAG_SPILL_BLKPTR 4
struct regentry{const char *name;uint16_t id,length;uint8_t swap;};static struct regentry regs[32];static unsigned nr;
struct layoutentry{const char *name;uint16_t ids[32];unsigned count,width;};static struct layoutentry layouts[3];static unsigned nl;
static uint8_t spillbytes[1024];static size_t spilllen;
static grub_err_t dnode_get(dnode_end_t *mdn,uint64_t obj,uint8_t type,dnode_end_t *out,struct grub_zfs_data *data){(void)mdn;(void)type;(void)data;memset(out,0,sizeof(*out));out->dn.pad3[0]=obj;return 0;}
static grub_err_t zap_lookup(dnode_end_t *dn,const char *name,uint64_t *value,struct grub_zfs_data *data,int ci){(void)data;(void)ci;if(dn->dn.pad3[0]==1 && !strcmp(name,ZFS_SA_ATTRS))*value=10;else if(dn->dn.pad3[0]==10 && !strcmp(name,"REGISTRY"))*value=11;else if(dn->dn.pad3[0]==10 && !strcmp(name,"LAYOUTS"))*value=12;else return grub_error(GRUB_ERR_FILE_NOT_FOUND,"missing mock object");return 0;}
static int zap_iterate_u64(dnode_end_t *dn,int(*hook)(const char*,uint64_t,struct grub_zfs_dir_ctx*),struct grub_zfs_data *data,struct grub_zfs_dir_ctx *ctx){unsigned i;(void)dn;(void)data;for(i=0;i<nr;++i)hook(regs[i].name,(uint64_t)regs[i].id|((uint64_t)regs[i].swap<<16)|((uint64_t)regs[i].length<<24),ctx);return 0;}
static int zap_iterate(dnode_end_t *dn,size_t namewidth,int(*hook)(const void*,size_t,const void*,size_t,size_t,void*),void *ctx,struct grub_zfs_data *data){unsigned i,j;uint8_t wire[64];(void)dn;(void)namewidth;(void)data;for(i=0;i<nl;++i){for(j=0;j<layouts[i].count;++j){wire[j*2]=(uint8_t)(layouts[i].ids[j]>>8);wire[j*2+1]=(uint8_t)layouts[i].ids[j];}hook(layouts[i].name,strlen(layouts[i].name)+1,wire,layouts[i].count,layouts[i].width,ctx);}return 0;}
static grub_err_t zio_read(blkptr_t *ptr,grub_zfs_endian_t e,void **out,size_t *size,struct grub_zfs_data *data){(void)ptr;(void)e;(void)data;*out=grub_malloc(spilllen);if(!*out)return grub_errno;memcpy(*out,spillbytes,spilllen);*size=spilllen;return 0;}
#include "../third_party/grub_fs_helper/zfs_sa_hosted.inc"
static void put16(uint8_t *b,size_t at,uint16_t n,int be){if(be)n=swap16(n);memcpy(b+at,&n,2);}static void put32(uint8_t *b,size_t at,uint32_t n,int be){if(be)n=swap32(n);memcpy(b+at,&n,4);}
static unsigned checks,failures;
#define CHECK(x) do{++checks;if(!(x)){++failures;fprintf(stderr,"SA control line %d: %s\n",__LINE__,#x);}}while(0)
static const char target[]="target/file.txt";
static void reset(uint8_t b[256],int be){memset(b,0,256);nr=1;regs[0]=(struct regentry){"ZPL_SYMLINK",17,0,3};nl=1;layouts[0]=(struct layoutentry){"10",{5,6,17},3,2};put32(b,0,0x2f505a,be);put16(b,4,10|(1<<10),be);put16(b,6,sizeof(target)-1,be);memcpy(b+24,target,sizeof(target)-1);grub_errno=0;}
int main(void){uint8_t b[256],saved[256];struct subvolume subvol={0};dnode_end_t dn={0};struct grub_zfs_data data={0};const void *out;size_t n;int endian,err,be;void *copy=NULL;
  CHECK(sizeof(dnode_phys_t)==512);
  for(be=0;be<2;++be){reset(b,be);CHECK(!hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,&endian) && n==15 && !memcmp(out,target,n) && endian==(be?0:-1));
    CHECK(!hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_MODE",&out,&n,&endian) && n==8 && out==b+8);
    reset(b,be);regs[1]=(struct regentry){"custom-variable",18,0,3};nr=2;layouts[0]=(struct layoutentry){"10",{18,5,6,17},4,2};put16(b,4,10|(2<<10),be);put16(b,6,5,be);put16(b,8,15,be);memcpy(b+16,"12345",5);memcpy(b+40,target,15);CHECK(!hosted_sa_lookup(&subvol,&dn,&data,b,55,"ZPL_SYMLINK",&out,&n,&endian) && n==15 && out==b+40 && !memcmp(out,target,n));
    put16(b,6,0,be);memcpy(b+32,target,15);grub_errno=0;CHECK(!hosted_sa_lookup(&subvol,&dn,&data,b,47,"ZPL_SYMLINK",&out,&n,&endian) && out==b+32);
  }
  reset(b,0);regs[0].id=65535;layouts[0].ids[2]=65535;CHECK(!hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL) && out==b+24);
  reset(b,0);memcpy(saved,b,256);CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,7,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);b[0]=1;CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);put16(b,4,10,0);CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);put16(b,4,10|(2<<10),0);CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);put16(b,6,16,0);CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);layouts[0].ids[1]=5;CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);layouts[0].ids[1]=600;CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);layouts[0].width=8;CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);layouts[0].name="11";CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);regs[1]=regs[0];nr=2;CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);regs[0].swap=5;CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_BAD_FS);
  reset(b,0);regs[0].name="another-attribute";CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,39,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_FILE_NOT_FOUND);
  reset(b,0);layouts[0].count=2;CHECK(hosted_sa_lookup(&subvol,&dn,&data,b,24,"ZPL_SYMLINK",&out,&n,NULL)==GRUB_ERR_FILE_NOT_FOUND);
  reset(b,0);dn.endian=-1;dn.dn.dn_nblkptr=1;dn.dn.dn_bonuslen=39;memcpy((char*)&dn.dn+192,b,39);CHECK(!hosted_sa_copy(&subvol,&dn,&data,"ZPL_SYMLINK",&copy,&n,NULL) && n==15 && !memcmp(copy,target,n));free(copy);copy=NULL;
  reset(b,0);dn.dn.dn_flags=4;dn.dn.dn_bonuslen=24;layouts[0].count=2;put16(b,6,0,0);memcpy((char*)&dn.dn+192,b,24);nl=2;layouts[1]=(struct layoutentry){"11",{17},1,2};spilllen=23;memset(spillbytes,0,sizeof(spillbytes));put32(spillbytes,0,0x2f505a,1);put16(spillbytes,4,11|(1<<10),1);put16(spillbytes,6,15,1);memcpy(spillbytes+8,target,15);grub_errno=0;
  CHECK(!hosted_sa_copy(&subvol,&dn,&data,"ZPL_SYMLINK",&copy,&n,&endian) && n==15 && endian==0 && !memcmp(copy,target,n));free(copy);copy=NULL;
  dn.dn.dn_bonuslen=193;grub_errno=0;CHECK(hosted_sa_copy(&subvol,&dn,&data,"ZPL_SYMLINK",&copy,&n,NULL)==GRUB_ERR_BAD_FS);
  dn.dn.dn_nblkptr=4;grub_errno=0;CHECK(hosted_sa_copy(&subvol,&dn,&data,"ZPL_SYMLINK",&copy,&n,NULL)==GRUB_ERR_BAD_FS);
  (void)saved;(void)err;printf("ZFS SA independent grammar: %u/%u passed\n",checks-failures,checks);return failures?1:0;
}
